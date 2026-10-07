"""API de trabajos del visor: las mismas rutas y respuestas que referencia/api_actual.py, debajo de
/<taller>/visor/api/ (el visor las pide con la ruta relativa `api/…`), con sesión y dentro del taller.

    GET    trabajos?proyecto=<id>          lista del proyecto
    POST   trabajos                        nuevo  {proyecto, texto, piezas, muebles, asignado, limite}
    PATCH  trabajos/<id>                   cambia {texto, estado, asignado, limite, piezas, muebles}
    DELETE trabajos/<id>
    POST   trabajos/<id>/fotos             cuerpo = la imagen (image/jpeg, image/png o image/webp)
    DELETE trabajos/<id>/fotos/<f>
    GET    fotos/<f>

Diferencias con api.py: el proyecto va por su id (dos pueden llamarse igual); `asignado` es el id de un miembro del
taller; quién anota y quién cambia el estado sale de la sesión (`autor` y `quien` del pedido no se usan). En la
respuesta, `autor`, `asignado` y `*_por` siguen siendo nombres, así el visor los muestra igual que antes.

Cualquier miembro ve, anota, cambia el estado y sube fotos; cambiar lo demás, borrar y quitar fotos ajenas es del
que lo anotó, el dueño o la oficina (`puede_editar`). Como en el resto de la app, el filtro por taller lo pone
DatoDeTaller: un id de otro taller es 404."""
import io
import json
import re
from datetime import date
from functools import wraps

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Case, IntegerField, Value, When
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from PIL import Image, UnidentifiedImageError

from proyectos.models import Proyecto
from talleres.archivos import abrir_de_taller
from talleres.limites import MENSAJES, permite
from talleres.models import Membresia
from talleres.roles import Rol, miembro

from .models import CambioDeEstado, Foto, Trabajo

ESTADOS = Trabajo.Estado.values
MAX_FOTO = 12 * 1024 * 1024
MAX_JSON = 256 * 1024
TIPOS_FOTO = {'image/jpeg': 'JPEG', 'image/png': 'PNG', 'image/webp': 'WEBP'}
EXTENSION = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}
UN_ANIO = 365 * 24 * 3600
GESTION = (Rol.DUENO, Rol.OFICINA)


class Rechazo(Exception):
    def __init__(self, codigo, error):
        super().__init__(error)
        self.codigo, self.error = codigo, error


def responder(codigo, obj=None):
    if obj is None:
        r = HttpResponse(status=codigo)
    else:
        r = JsonResponse(obj, status=codigo, safe=False, json_dumps_params={'ensure_ascii': False})
    r['Cache-Control'] = 'no-store'
    return r


def api(vista):
    """Miembro del taller; los errores salen como {"error": …} igual que en api.py."""
    @miembro
    @wraps(vista)
    def envuelta(request, *args, **kwargs):
        try:
            return vista(request, *args, **kwargs)
        except Rechazo as e:
            return responder(e.codigo, {'error': e.error})
        except Http404:
            return responder(404, {'error': 'no existe'})
    return envuelta


def solo(request, *metodos):
    if request.method not in metodos:
        raise Rechazo(405, 'método no admitido')


def puede_editar(request, trabajo):
    return request.membresia.rol in GESTION or (trabajo.autor_id is not None and trabajo.autor_id == request.user.pk)


def exigir(request, funcion):
    if not permite(request.taller, funcion):
        raise Rechazo(403, MENSAJES[funcion])


# ---------------------------------------------------------------- formato

def hora(dt):
    return timezone.localtime(dt).strftime('%Y-%m-%d %H:%M') if dt else None


def nombre(usuario):
    return str(usuario) if usuario else None


def a_dic(request, t):
    return {
        'id': t.pk, 'proyecto': t.proyecto_id, 'texto': t.texto, 'estado': t.estado,
        'autor': nombre(t.autor), 'asignado': nombre(t.asignado), 'asignado_id': t.asignado_id,
        'creado': hora(t.creado), 'limite': t.limite.isoformat() if t.limite else None,
        'iniciado_por': nombre(t.iniciado_por), 'iniciado_en': hora(t.iniciado_en),
        'hecho_por': nombre(t.hecho_por), 'hecho_en': hora(t.hecho_en),
        'instalado_por': nombre(t.instalado_por), 'instalado_en': hora(t.instalado_en),
        'piezas': t.piezas, 'muebles': t.muebles,
        'fotos': [str(f.pk) for f in t.fotos.all()],
        'puede_editar': puede_editar(request, t),
    }


def trabajos():
    return (Trabajo.objects
            .select_related('autor', 'asignado', 'iniciado_por', 'hecho_por', 'instalado_por')
            .prefetch_related('fotos'))


def uno(request, id):
    return a_dic(request, trabajos().get(pk=id))


# ---------------------------------------------------------------- validación (la de api.py)

def leer_json(request):
    if int(request.META.get('CONTENT_LENGTH') or 0) > MAX_JSON:
        raise Rechazo(400, 'se esperaba un objeto JSON')
    try:
        d = json.loads(request.body or b'null')
    except ValueError:
        d = None
    if not isinstance(d, dict):
        raise Rechazo(400, 'se esperaba un objeto JSON')
    return d


def validar(d, nuevo):
    if nuevo and not (isinstance(d.get('texto'), str) and d['texto'].strip()):
        raise Rechazo(400, 'falta el texto')
    if 'texto' in d and not (isinstance(d['texto'], str) and d['texto'].strip() and len(d['texto']) <= 4000):
        raise Rechazo(400, 'texto no válido')
    if d.get('limite') is not None:
        if not (isinstance(d['limite'], str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', d['limite'])):
            raise Rechazo(400, 'limite debe ser AAAA-MM-DD')
        try:
            date.fromisoformat(d['limite'])
        except ValueError:
            raise Rechazo(400, 'limite debe ser AAAA-MM-DD')
    if 'estado' in d and d['estado'] not in ESTADOS:
        raise Rechazo(400, f"estado no válido (se espera: {', '.join(ESTADOS)})")
    for k in ('piezas', 'muebles'):
        if k in d and not (isinstance(d[k], list) and len(d[k]) <= 500
                           and all(isinstance(x, str) and len(x) <= 200 for x in d[k])):
            raise Rechazo(400, f'{k} no válido')
    a = d.get('asignado')
    if a is not None and (isinstance(a, bool) or not isinstance(a, int)):
        raise Rechazo(400, 'asignado no válido')


def asignable(usuario_id):
    """Solo gente del taller, con la membresía activa (Membresia filtra por el taller del pedido)."""
    if not Membresia.objects.filter(usuario_id=usuario_id, activa=True).exists():
        raise Rechazo(400, 'asignado no es del taller')
    return usuario_id


# ---------------------------------------------------------------- vistas

@api
def lista_o_nuevo(request, taller):
    solo(request, 'GET', 'POST')
    if request.method == 'GET':
        try:
            proyecto = int(request.GET.get('proyecto', ''))
        except ValueError:
            raise Rechazo(400, 'falta el proyecto')
        get_object_or_404(Proyecto, pk=proyecto)
        orden = Case(*(When(estado=e, then=Value(i)) for i, e in enumerate(ESTADOS)), output_field=IntegerField())
        lista = trabajos().filter(proyecto_id=proyecto).order_by(orden, '-pk')
        return responder(200, [a_dic(request, t) for t in lista])

    exigir(request, 'trabajos')
    d = leer_json(request)
    p = d.get('proyecto')
    if isinstance(p, bool) or not isinstance(p, int):
        raise Rechazo(400, 'falta el proyecto')
    validar(d, nuevo=True)
    proyecto = get_object_or_404(Proyecto, pk=p)
    t = Trabajo.objects.create(
        proyecto=proyecto, texto=d['texto'], autor=request.user,
        asignado_id=asignable(d['asignado']) if d.get('asignado') is not None else None,
        limite=d.get('limite') or None, piezas=d.get('piezas', []), muebles=d.get('muebles', []))
    return responder(201, uno(request, t.pk))


@api
def trabajo(request, taller, id):
    solo(request, 'PATCH', 'DELETE')
    exigir(request, 'trabajos')
    with transaction.atomic():
        t = get_object_or_404(Trabajo.objects.select_for_update(), pk=id)
        if request.method == 'DELETE':
            if not puede_editar(request, t):
                raise Rechazo(403, 'Solo quien lo anotó, el dueño o la oficina pueden borrar este trabajo.')
            archivos = [f.archivo.name for f in t.fotos.all()]
            t.delete()
            transaction.on_commit(lambda: [default_storage.delete(a) for a in archivos])
            return responder(204)

        d = leer_json(request)
        validar(d, nuevo=False)
        cambios = {k for k in ('texto', 'asignado', 'limite', 'piezas', 'muebles') if k in d}
        if 'asignado' in d and d['asignado'] == t.asignado_id:
            cambios.discard('asignado')            # el de antes vale aunque ya no esté en el taller
        if 'limite' in d and (d['limite'] or None) == (t.limite.isoformat() if t.limite else None):
            cambios.discard('limite')
        for k in ('texto', 'piezas', 'muebles'):
            if k in d and d[k] == getattr(t, k):
                cambios.discard(k)
        if cambios and not puede_editar(request, t):
            raise Rechazo(403, 'Solo quien lo anotó, el dueño o la oficina pueden cambiar este trabajo.')
        if 'texto' in cambios:
            t.texto = d['texto']
        if 'asignado' in cambios:
            t.asignado_id = asignable(d['asignado']) if d['asignado'] is not None else None
        if 'limite' in cambios:
            t.limite = d['limite'] or None
        for k in ('piezas', 'muebles'):
            if k in cambios:
                setattr(t, k, d[k])
        if 'estado' in d:
            ahora = timezone.now()
            anterior = t.cambiar_estado(d['estado'], request.user, ahora)
            if anterior is not None:
                CambioDeEstado.objects.create(trabajo=t, de=anterior, a=t.estado, usuario=request.user, cuando=ahora)
        t.save()
    return responder(200, uno(request, t.pk))


def imagen_valida(datos, tipo):
    """El formato real de la imagen (no el que dice el pedido), o Rechazo."""
    try:
        with Image.open(io.BytesIO(datos)) as img:
            formato = img.format
            img.verify()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise Rechazo(415, 'formato de imagen no admitido')
    if formato not in EXTENSION or TIPOS_FOTO[tipo] != formato:
        raise Rechazo(415, 'formato de imagen no admitido')
    return formato


@api
def fotos(request, taller, id):
    solo(request, 'POST')
    exigir(request, 'trabajos')
    exigir(request, 'fotos_de_trabajos')
    tipo = (request.content_type or '').strip().lower()
    if tipo not in TIPOS_FOTO:
        raise Rechazo(415, 'formato de imagen no admitido')
    largo = int(request.META.get('CONTENT_LENGTH') or 0)
    if largo <= 0 or largo > MAX_FOTO:
        raise Rechazo(413, 'imagen vacía o demasiado grande')
    t = get_object_or_404(Trabajo, pk=id)
    datos = request.read(MAX_FOTO + 1)        # sin request.body: su tope (DATA_UPLOAD_MAX_MEMORY_SIZE) es de 2,5 MB
    if not datos or len(datos) > MAX_FOTO:
        raise Rechazo(413, 'imagen vacía o demasiado grande')
    formato = imagen_valida(datos, tipo)
    foto = Foto(trabajo=t, tamano=len(datos), subida_por=request.user)
    foto.taller = request.taller
    foto.archivo.save(f'trabajo-{t.pk}.{EXTENSION[formato]}', ContentFile(datos), save=False)
    try:
        foto.save()
    except BaseException:
        default_storage.delete(foto.archivo.name)
        raise
    return responder(200, uno(request, t.pk))


@api
def foto(request, taller, id, foto_id):
    solo(request, 'DELETE')
    exigir(request, 'trabajos')
    with transaction.atomic():
        f = get_object_or_404(Foto.objects.select_related('trabajo'), pk=foto_id, trabajo_id=id)
        if f.subida_por_id != request.user.pk and not puede_editar(request, f.trabajo):
            raise Rechazo(403, 'Solo quien la subió, quien anotó el trabajo, el dueño o la oficina pueden quitarla.')
        archivo = f.archivo.name
        f.delete()
        transaction.on_commit(lambda: default_storage.delete(archivo))
    return responder(200, uno(request, id))


@api
def ver_foto(request, taller, foto_id):
    solo(request, 'GET')
    f = get_object_or_404(Foto, pk=foto_id)
    r = abrir_de_taller(request, f.archivo.name)
    r['Cache-Control'] = f'private, max-age={UN_ANIO}, immutable'      # cada foto tiene su id: no cambia
    return r
