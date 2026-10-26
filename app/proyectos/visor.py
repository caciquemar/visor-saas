"""El visor (visor/index.html) servido por la app, para el taller y para el link del cliente.

El visor pide sus datos con rutas relativas (`data/…`); acá se atienden esas mismas rutas debajo de donde se sirve la
página, así index.html cambia lo mínimo:

    /<taller>/visor/                      la página (con login, como todo /<taller>/)
    /<taller>/visor/data/index.json       proyectos con versión lista
    /<taller>/visor/data/<id>/<ruta>      resultado/ de la versión actual del proyecto <id>
    /<taller>/visor/api/…                 trabajos a realizar (trabajos/api.py)
    /c/<código>/                          la página en modo cliente (sin login; el middleware pone el taller del link)
    /c/<código>/data/cliente.json         la versión cliente (sin números de mecanizado)
    /c/<código>/data/clientes/<cc>/x.glb  modelos para realidad aumentada
    /c/<código>/data/texturas/<archivo>   texturas
    /c/<código>/data/opciones/<id>.<ext>  texturas de los tableros que ofrece el probador de colores (ficha 14)
    /c/<código>/data/combinaciones/<clave>/x.glb   AR de una combinación del probador
    /c/<código>/probador/ar, …/elegir     probador: pedir la AR de una combinación, "Me gusta esta"

Por /c/ nunca sale proyecto.json: solo lo que está en la lista blanca de `dato_cliente`.
"""
import json
import mimetypes
import re
from functools import lru_cache

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from avance.models import procesos as procesos_del_taller
from talleres.archivos import abrir_de_taller
from talleres.iconos import ICONOS
from talleres.limites import permite
from talleres.menu import pantallas
from talleres.models import Membresia
from talleres.roles import con_permiso, miembro

from . import probador, tareas
from .models import Combinacion, EleccionCliente, GrupoDeColor, LinkCliente, Material, Proyecto, Version, para_produccion

mimetypes.add_type('model/gltf-binary', '.glb')
INDEX = settings.RAIZ / 'visor' / 'index.html'
MARCA_CONFIG = '/*__VISOR__*/null'
UNA_SEMANA = 7 * 24 * 3600


@lru_cache(maxsize=4)
def _plantilla(modificado):
    texto = INDEX.read_text(encoding='utf-8')
    if MARCA_CONFIG not in texto:
        raise RuntimeError(f'visor/index.html no tiene la marca {MARCA_CONFIG}')
    return texto


def pagina(config):
    """index.html con la configuración de la app en `window.VISOR`."""
    texto = json.dumps(config, ensure_ascii=False).replace('<', '\\u003c')    # nada de </script> adentro
    r = HttpResponse(_plantilla(INDEX.stat().st_mtime_ns).replace(MARCA_CONFIG, texto, 1),
                     content_type='text/html; charset=utf-8')
    r['Cache-Control'] = 'no-cache'
    r['Referrer-Policy'] = 'no-referrer'          # el código del link no viaja a los CDN ni a otros sitios
    return r


def servir(request, ruta):
    """Un archivo del taller del pedido (abrir_de_taller da 404 si no es suyo), con la caché del nginx actual:
    JSON y GLB se revalidan; las texturas de una versión no cambian."""
    r = abrir_de_taller(request, ruta)
    if ruta.endswith(('.json', '.glb')):
        r['Cache-Control'] = 'no-cache'
    elif '/texturas/' in ruta:
        r['Cache-Control'] = f'private, max-age={UNA_SEMANA}'
    return r


def version_lista(proyecto_id):
    p = get_object_or_404(Proyecto.objects.select_related('version_actual'), pk=proyecto_id)
    v = p.version_actual
    if v is None or v.estado != Version.Estado.LISTO or not v.archivo_proyecto:
        raise Http404('El proyecto no tiene una versión lista')
    return p, v


def vigentes():
    return (LinkCliente.objects.filter(anulado__isnull=True)
            .filter(Q(vence__isnull=True) | Q(vence__gt=timezone.now())).order_by('-creado'))


def url_de_link(request, link):
    return request.build_absolute_uri(f'/c/{link.codigo}/')


# ---------------------------------------------------------------- taller

def url_de_etiquetas(request):
    """Pantalla de etiquetas de un proyecto, con {id} para que el visor ponga el que se está viendo."""
    return reverse('taller:etiquetas:imprimir', kwargs={'taller': request.taller.slug, 'id': 0}).replace('/0/', '/{id}/')


def menu_de(request):
    """El menú del visor: el mismo que el ☰ de las demás páginas (templates/menu.html), con el dibujo de cada ícono
    (talleres/iconos.py) porque el visor lo arma en JavaScript."""
    return [dict(x, actual=x['nombre'] == 'Visor', icono=ICONOS.get(x.get('icono'), '')) for x in pantallas(request)]


def formato_para_el_visor():
    from etiquetas.vistas import formato_para_el_visor as formato
    return formato()


@con_permiso('visor')
def visor(request, taller):
    """Con trabajos (trabajos/api.py): quién es el que mira, la gente del taller para "Para quién" y el token CSRF
    que el visor manda al anotar o cambiar."""
    equipo = Membresia.objects.filter(activa=True).select_related('usuario')
    return pagina({
        'trabajos': permite(request.taller, 'trabajos'),
        'fotos': permite(request.taller, 'fotos_de_trabajos'),
        'yo': {'id': request.user.pk, 'nombre': str(request.user)},
        'equipo': sorted(({'id': m.usuario_id, 'nombre': str(m.usuario)} for m in equipo),
                         key=lambda x: x['nombre'].lower()),
        'csrf': get_token(request),
        'sinCanto': request.taller.color_sin_canto,
        'marca': {'nombre': request.taller.nombre},
        'menu': menu_de(request),
        'etiquetas': {'pantalla': url_de_etiquetas(request), 'formato': formato_para_el_visor()},
        'avance': {'puesto': reverse('taller:avance:puesto', kwargs={'taller': request.taller.slug}),
                   'api': reverse('taller:avance:puesto', kwargs={'taller': request.taller.slug}) + 'api/',
                   # para la lista "Avance" del visor: elegir un proceso pinta lo que lo cumplió
                   'procesos': [{'id': e.pk, 'nombre': e.nombre} for e in procesos_del_taller() if e.activa]},
        'salir': reverse('salir'),
        'cuenta': reverse('taller:cuenta', kwargs={'taller': request.taller.slug}),
        'cambiar': reverse('entrar') + '?cambiar=1',         # celular compartido: entra otro
    })


@miembro
def indice(request, taller):
    """Lo que en el visor de siempre es data/index.json, armado desde la base."""
    links = {}
    for link in vigentes():
        links.setdefault(link.proyecto_id, link)      # el más nuevo
    listos = (Proyecto.objects.filter(version_actual__estado=Version.Estado.LISTO)
              .exclude(version_actual__archivo_proyecto='').order_by('nombre', 'pk'))
    # los que están en desarrollo o archivados no se ven (ficha 22), salvo el que se abrió desde su pantalla (?p=)
    pedido = request.GET.get('p', '')
    proyectos = listos.filter(Q(pk__in=para_produccion(listos)) | Q(pk=int(pedido) if pedido.isdigit() else 0))
    lista = [{'id': p.pk, 'proyecto': p.nombre if p.en_produccion and not p.archivado_en
              else f'{p.nombre} ({p.get_estado_display().lower()})', 'archivo': f'{p.pk}/proyecto.json',
              'link': url_de_link(request, links[p.pk]) if p.pk in links else None} for p in proyectos]
    r = JsonResponse(lista, safe=False, json_dumps_params={'ensure_ascii': False})
    r['Cache-Control'] = 'no-cache'
    return r


@miembro
def dato(request, taller, id, ruta):
    _, v = version_lista(id)
    archivo = v.archivo_proyecto if ruta == 'proyecto.json' else f'{v.carpeta()}resultado/{ruta}'
    return servir(request, archivo)


def sin_colores(request, **kwargs):
    """data/materiales.json del visor de siempre: los colores del taller ya vienen dentro de cada proyecto."""
    return JsonResponse({})


miembro_sin_colores = miembro(sin_colores)


@miembro
def manifest(request, taller):
    inicio = f'/{request.taller.slug}/visor/'
    r = JsonResponse({
        'name': 'Visor', 'short_name': 'Visor', 'lang': 'es-AR',
        'start_url': inicio, 'scope': inicio, 'display': 'standalone',
        'background_color': '#DCE1E4', 'theme_color': '#DCE1E4',
        'icons': [{'src': static(f'visor/icono-{n}.png'), 'sizes': f'{n}x{n}',
                   'type': 'image/png', 'purpose': 'any maskable'} for n in (192, 512)],
    })
    r['Content-Type'] = 'application/manifest+json'
    return r


# ---------------------------------------------------------------- link del cliente

def link_o_404(request):
    link = getattr(request, 'link_cliente', None)
    if link is None:
        raise Http404('Este link no existe o ya no está disponible')
    return link


def no_disponible(request):
    return render(request, 'proyectos/link_no_disponible.html', status=404)


def es_del_taller(request):
    """El taller mirando su propio link ("Ver como cliente") no suma visitas."""
    return request.user.is_authenticated and Membresia.objects.filter(usuario=request.user, activa=True).exists()


@require_GET
def cliente(request, codigo):
    link = getattr(request, 'link_cliente', None)
    if link is None:
        return no_disponible(request)
    try:
        version_lista(link.proyecto_id)
    except Http404:
        return no_disponible(request)
    if not es_del_taller(request):
        LinkCliente.objects.filter(pk=link.pk).update(visitas=F('visitas') + 1, ultima_visita=timezone.now())
    taller = request.taller
    config = {
        'cliente': True, 'trabajos': False, 'sinCanto': taller.color_sin_canto,
        'marca': {'nombre': taller.nombre, 'color': taller.color or None, 'logo': 'logo' if taller.logo else None},
        'pie': {'nombre': settings.MARCA_SERVICIO, 'url': settings.MARCA_URL or None},
    }
    p, v = version_lista(link.proyecto_id)
    grupos = probador.para_el_visor(probador.grupos_vigentes(p, probador.leer_cliente(v)))
    if grupos:          # probador de colores (ficha 14): solo en el link del cliente
        config.update(probador=grupos, csrf=get_token(request))
    return pagina(config)


@require_GET
def dato_cliente(request, codigo, ruta):
    link = link_o_404(request)
    p, v = version_lista(link.proyecto_id)
    if ruta == 'materiales.json':
        return sin_colores(request)
    if ruta == 'cliente.json':
        archivo = f'clientes/{p.codigo_cliente}.json'
    elif (re.fullmatch(rf'clientes/{re.escape(p.codigo_cliente)}/[\w.-]+\.glb', ruta)
          or re.fullmatch(r'texturas/[\w.-]+', ruta)):
        archivo = ruta
    elif m := re.fullmatch(rf'{probador.CARPETA_OPCIONES}/(\d+)\.\w+', ruta):
        return textura_de_opcion(request, p, int(m.group(1)), ruta)
    elif m := re.fullmatch(rf'{probador.CARPETA_COMBINACIONES}/(\w+)/[\w.-]+\.glb', ruta):
        comb = v.combinaciones.filter(clave=m.group(1), estado=Combinacion.Estado.LISTA).first()
        if comb is None or ruta not in comb.ar.values():
            raise Http404('No existe el archivo')
        archivo = ruta
    else:
        raise Http404('No existe el archivo')
    return servir(request, f'{v.carpeta()}resultado/{archivo}')


def textura_de_opcion(request, proyecto, material_id, ruta):
    """La textura de un tablero de la biblioteca, solo si el taller lo ofrece en el probador de este proyecto."""
    ofrecidos = {pk for g in GrupoDeColor.objects.filter(proyecto=proyecto) for pk in g.opciones}
    m = Material.objects.filter(pk=material_id, tipo=Material.Tipo.TABLERO).exclude(textura='').first()
    if material_id not in ofrecidos or m is None or probador.textura_de(m) != ruta:
        raise Http404('No existe el archivo')
    r = abrir_de_taller(request, m.textura.name)
    r['Cache-Control'] = 'no-cache'          # el taller puede cambiar la imagen
    return r


# ---------------------------------------------------------------- probador de colores (ficha 14)

NUEVAS_POR_IP = 10          # combinaciones nuevas por hora desde una misma IP (cada una es trabajo para la cola)
ELECCIONES_POR_IP = 10      # "Me gusta esta" por hora desde una misma IP


def pasar_tope(request, que, tope):
    """False si esta IP ya hizo `tope` veces `que` en la última hora con este link; si no, cuenta una más."""
    from talleres.vistas import ip_de
    k = f'probador-{que}:{request.link_cliente.pk}:{ip_de(request)}'
    if cache.get(k, 0) >= tope:
        return False
    cache.add(k, 0, timeout=3600)
    try:
        cache.incr(k)
    except ValueError:
        cache.set(k, 1, timeout=3600)
    return True


def json_del_pedido(request):
    try:
        datos = json.loads(request.body or b'{}')
    except ValueError:
        datos = None
    return datos if isinstance(datos, dict) else None


def del_probador(request):
    """(proyecto, versión, grupos vigentes) del link; 404 si no hay probador."""
    link = link_o_404(request)
    p, v = version_lista(link.proyecto_id)
    vigentes = probador.grupos_vigentes(p, probador.leer_cliente(v))
    if not vigentes:
        raise Http404('Este proyecto no tiene colores para probar')
    return p, v, vigentes


@require_POST
def probador_ar(request, codigo):
    """Modelos de AR de una combinación: {estado: 'lista', ar} | {estado: 'preparando'} | {estado: 'celular'}
    (sin modelo guardado: el visor lo arma en el celular). El visor repite el pedido hasta que deja de preparar."""
    p, v, vigentes = del_probador(request)
    datos = json_del_pedido(request)
    if datos is None:
        return JsonResponse({'error': 'Pedido inválido'}, status=400)
    elecciones = probador.normalizar(datos.get('elecciones'), vigentes)
    if not elecciones:
        return JsonResponse({'estado': 'lista', 'ar': {}})        # como está: los modelos de siempre
    k = probador.clave_de(elecciones, vigentes)
    comb = v.combinaciones.filter(clave=k).first()
    if comb is None:
        if v.combinaciones.count() >= probador.LIMITE_COMBINACIONES or not pasar_tope(request, 'ar', NUEVAS_POR_IP):
            return JsonResponse({'estado': 'celular'})
        try:
            with transaction.atomic():
                comb = Combinacion.objects.create(version=v, clave=k, elecciones=elecciones)
                tareas.encolar_combinacion(comb)
        except IntegrityError:          # la pidió otro al mismo tiempo
            comb = v.combinaciones.get(clave=k)
        comb.refresh_from_db()          # con la cola en modo inmediato ya quedó generada
    if comb.estado == Combinacion.Estado.LISTA:
        return JsonResponse({'estado': 'lista', 'ar': comb.ar})
    if comb.estado == Combinacion.Estado.ERROR:
        return JsonResponse({'estado': 'celular'})
    return JsonResponse({'estado': 'preparando'})


@require_POST
def probador_elegir(request, codigo):
    """"Me gusta esta": guarda la combinación con el nombre y el comentario del cliente."""
    p, v, vigentes = del_probador(request)
    datos = json_del_pedido(request)
    if datos is None:
        return JsonResponse({'error': 'Pedido inválido'}, status=400)
    nombre = str(datos.get('nombre') or '').strip()[:80]
    comentario = str(datos.get('comentario') or '').strip()[:1000]
    if not nombre:
        return JsonResponse({'error': 'Escribí tu nombre.'}, status=400)
    if not pasar_tope(request, 'elegir', ELECCIONES_POR_IP):
        return JsonResponse({'error': 'Ya mandaste varias. Probá de nuevo en un rato.'}, status=429)
    elecciones = probador.normalizar(datos.get('elecciones'), vigentes)
    EleccionCliente.objects.create(proyecto=p, version=v, link=request.link_cliente, nombre=nombre,
                                   comentario=comentario, elecciones=probador.elegidos(elecciones, vigentes))
    return JsonResponse({'ok': True})


@require_GET
def logo_cliente(request, codigo):
    link_o_404(request)
    if not request.taller.logo:
        raise Http404('El taller no tiene logo')
    r = abrir_de_taller(request, request.taller.logo.name)
    r['Cache-Control'] = 'no-cache'
    return r
