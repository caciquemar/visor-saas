"""API del puesto (/<taller>/puesto/api/…) y del avance en el visor (/<taller>/visor/api/avance). Cualquier miembro
del taller; reabrir un mueble es del dueño o la oficina. Como en el resto de la app, el filtro por taller lo pone
DatoDeTaller: ids y códigos de otro taller no se encuentran.

    POST puesto/api/marcar                 {texto, etapa, proyecto?, ubicacion?}   pieza en una etapa (y lugar)
    POST puesto/api/deshacer               {marca}
    POST puesto/api/mueble                 {texto, proyecto?}          qué mueble es y cuánto le falta
    GET  puesto/api/mueble?proyecto=&mueble=
    POST puesto/api/terminar               {proyecto, mueble, bultos, motivo, ubicacion?}
    POST puesto/api/tareas                 {texto, proyecto?}          tareas sin instalar de una pieza o mueble
    POST puesto/api/armar                  {texto, proyecto?, ubicacion?, etapa?}   el mueble entero en Armado (o en un
                                           proceso del taller por mueble)
    POST puesto/api/embalar                {texto, proyecto?, ubicacion?}   embalado al escanear, con 1 bulto
    POST puesto/api/bultos                 {proyecto, mueble, bultos}   corregir la cantidad (ningún bulto cargado)
    POST puesto/api/control                {texto, proyecto?} lee; {proyecto, mueble, resultados} guarda
    POST puesto/api/instalacion            {proyecto, mueble}          la tarjeta de instalar
    POST puesto/api/instalar               {texto, proyecto?}          instalado al escanear
    POST puesto/api/desinstalar            {proyecto, mueble}          dueño u oficina
    POST puesto/api/instalaciones/<id>/fotos   cuerpo = la imagen
    GET  puesto/api/fotos-de-instalacion/<id>
    POST puesto/api/anotar                 {proyecto, mueble, panel?, proceso?, texto, tarea?}   anotación
    POST puesto/api/anotaciones/<id>/fotos cuerpo = la imagen
    GET  puesto/api/fotos-de-anotacion/<id>
    GET  visor/api/entrega?proyecto=<id>   el paso de cada mueble (bloque del mueble en el visor), con sus anotaciones
    GET  visor/api/avance-proceso?proyecto=<id>&proceso=<id>   qué muebles y piezas cumplieron un proceso (3D)
    POST puesto/api/reabrir                {proyecto, mueble}
    GET  puesto/api/cargas/<id>
    POST puesto/api/cargas/<id>/bulto      {texto}
    POST puesto/api/cargas/<id>/deshacer   {bulto}
    POST puesto/api/cargas/nueva/bulto     {texto}                     crea una carga libre con ese bulto
    POST puesto/api/cargas/<id>/salir      {motivo?}                   cerrar la carga (sale aunque falte algo)
    GET  visor/api/avance?proyecto=<id>
"""
from django.http import Http404
from django.shortcuts import get_object_or_404

from talleres.archivos import abrir_de_taller
from talleres.roles import Rol
from trabajos.api import (EXTENSION, MAX_FOTO, TIPOS_FOTO, UN_ANIO, Rechazo, api, imagen_valida, leer_json,
                          responder, solo, uno)

from . import acciones, entrega
from .calculo import avance, piezas_de, piezas_nuevas, ubicaciones
from .models import FotoDeAnotacion, FotoDeInstalacion, Marca, Ubicacion, procesos as procesos_del_taller
from .pasos import COLORES_AVANCE, NOMBRES_AVANCE, avance_de_proceso, pasos

GESTION = (Rol.DUENO, Rol.OFICINA)


def entero(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def texto_de(d):
    t = d.get('texto')
    if not isinstance(t, str) or not t.strip() or len(t) > 500:
        raise Rechazo(400, 'falta lo leído')
    return t


def ubicacion_de(d):
    u = d.get('ubicacion')
    return None if u in (None, '') else entero(u) if not isinstance(u, bool) else -1


def proyecto_de(d):
    p = d.get('proyecto')
    return None if p in (None, '') else entero(p) if not isinstance(p, bool) else None


@api
def marcar(request, taller):
    solo(request, 'POST')
    d = leer_json(request)
    return responder(200, acciones.marcar(request.user, request.taller.slug, texto_de(d), entero(d.get('etapa')),
                                          proyecto_de(d), ubicacion_de(d)))


@api
def deshacer(request, taller):
    """Una marca, o varias (`marcas`: lo que marcó "Armado" de un mueble entero)."""
    solo(request, 'POST')
    d = leer_json(request)
    if isinstance(d.get('marcas'), list):
        ids = [entero(x) for x in d['marcas'][:500]]
        hechas = [acciones.deshacer(request.user, i) for i in ids if Marca.objects.filter(
            pk=i, deshecha_en__isnull=True).exists()] if all(isinstance(i, int) for i in ids) else None
        if hechas is None:
            raise Rechazo(400, 'marcas no válidas')
        return responder(200, {'resultado': 'ok', 'deshechas': len(hechas)})
    return responder(200, acciones.deshacer(request.user, entero(d.get('marca'))))


@api
def mueble(request, taller):
    if request.method == 'GET':
        p = acciones.proyecto_o_rechazo(entero(request.GET.get('proyecto')))
        return responder(200, acciones.estado_del_mueble(p, request.GET.get('mueble', '')))
    solo(request, 'POST')
    d = leer_json(request)
    return responder(200, acciones.mueble_leido(request.taller.slug, texto_de(d), proyecto_de(d)))


@api
def terminar(request, taller):
    solo(request, 'POST')
    d = leer_json(request)
    return responder(200, acciones.terminar(request.user, entero(d.get('proyecto')), d.get('mueble'),
                                            d.get('bultos'), d.get('motivo'), ubicacion_de(d)))


@api
def tareas(request, taller):
    """Modo "Tareas" del puesto: las tareas sin instalar de la pieza o el mueble leído, como las da la API de
    tareas del visor (para pasarlas de estado con PATCH visor/api/trabajos/<id>)."""
    solo(request, 'POST')
    d = leer_json(request)
    leido = acciones.tareas_de_lo_leido(request.taller.slug, texto_de(d), proyecto_de(d))
    if isinstance(leido, dict):
        return responder(200, leido)
    proyecto, que, abiertas = leido
    return responder(200, {'resultado': 'ok', 'proyecto': acciones.proyecto_a_dic(proyecto), **que,
                           'tareas': [uno(request, t.pk) for t in abiertas]})


@api
def reabrir(request, taller):
    solo(request, 'POST')
    if request.membresia.rol not in GESTION:
        raise Rechazo(403, 'Reabrir un mueble es del dueño o la oficina.')
    d = leer_json(request)
    return responder(200, acciones.reabrir(request.user, entero(d.get('proyecto')), d.get('mueble')))


@api
def carga(request, taller, id):
    solo(request, 'GET')
    return responder(200, acciones.carga_a_dic(acciones.carga_o_rechazo(id)))


@api
def bulto(request, taller, id):
    solo(request, 'POST')
    d = leer_json(request)
    return responder(200, acciones.bulto_leido(request.user, request.taller.slug, id, texto_de(d)))


@api
def deshacer_bulto(request, taller, id):
    solo(request, 'POST')
    return responder(200, acciones.deshacer_bulto(request.user, id, entero(leer_json(request).get('bulto'))))


@api
def avance_visor(request, taller):
    """Para el visor: por panel, las etapas hechas; por mueble, el % y si está terminado; las piezas nuevas de la
    versión. `final` es la etapa de armado (las piezas que la tienen se pintan con otro tono). Si el taller usa
    ubicaciones (ficha 17): `lugares` por panel (dónde quedó, quién y cuándo) y, por mueble, cuántas piezas hay en
    cada lugar y cuántas sin ubicar."""
    solo(request, 'GET')
    p = acciones.proyecto_o_rechazo(entero(request.GET.get('proyecto')))
    piezas = piezas_de(p)
    if not piezas:
        raise Http404()
    a = avance(p, piezas)
    armado = acciones.etapa_de_armado()
    lugares, por_mueble = {}, {}
    if Ubicacion.objects.exists():
        donde, _ = ubicaciones(p)
        for x in piezas:
            u = donde.get(x['huella'])
            cuenta = por_mueble.setdefault(x['panel']['mueble'], {})
            nombre_ = u.ubicacion.nombre if u else ''
            cuenta[nombre_] = cuenta.get(nombre_, 0) + 1
            if u:
                lugares[x['panel']['id']] = {'lugar': nombre_, 'por': str(u.por) if u.por else None,
                                             'cuando': acciones.hora(u.cuando)}
    return responder(200, {
        'etapas': [{'id': e.pk, 'nombre': e.nombre} for e in a['etapas']],
        'final': armado.pk if armado else None,
        'pct': a['total']['pct'],
        'paneles': a['paneles'],
        'muebles': {n: {'pct': m['pct'], 'piezas': m['piezas'],
                        'por_etapa': [m['por_etapa'][e.pk] for e in a['etapas']],
                        'terminado': bool(m['fin']),
                        'lugares': sorted(([k, v] for k, v in por_mueble.get(n, {}).items() if k),
                                          key=lambda kv: -kv[1]),
                        'sin_lugar': por_mueble.get(n, {}).get('', 0)} for n, m in a['muebles'].items()},
        'lugares': lugares if Ubicacion.objects.exists() else None,
        'nuevas': [x['panel']['id'] for x in piezas_nuevas(p, piezas)],
    })


# ---------------------------------------------------------------- ficha 18: del armado a la instalación

@api
def armar(request, taller):
    solo(request, 'POST')
    d = leer_json(request)
    return responder(200, entrega.armar_mueble(request.user, request.taller.slug, texto_de(d), proyecto_de(d),
                                               ubicacion_de(d), entero(d.get('etapa')) if d.get('etapa') else None))


@api
def embalar(request, taller):
    solo(request, 'POST')
    d = leer_json(request)
    return responder(200, entrega.embalar(request.user, request.taller.slug, texto_de(d), proyecto_de(d),
                                          ubicacion_de(d)))


@api
def bultos(request, taller):
    solo(request, 'POST')
    d = leer_json(request)
    return responder(200, entrega.cambiar_bultos(request.user, entero(d.get('proyecto')), d.get('mueble'),
                                                 d.get('bultos')))


@api
def control(request, taller):
    solo(request, 'POST')
    d = leer_json(request)
    if 'resultados' in d:
        return responder(200, entrega.controlar(request.user, request.taller, entero(d.get('proyecto')),
                                                d.get('mueble'), d.get('resultados')))
    return responder(200, entrega.control_leido(request.taller.slug, texto_de(d), proyecto_de(d)))


def tarjeta_instalacion(request, datos, abiertas):
    if datos.get('resultado') == 'error':
        return responder(200, datos)
    return responder(200, {**datos, 'tareas': [uno(request, t.pk) for t in abiertas]})


@api
def instalacion(request, taller):
    solo(request, 'POST')
    d = leer_json(request)
    return tarjeta_instalacion(request, *entrega.estado_instalacion(
        acciones.proyecto_o_rechazo(entero(d.get('proyecto'))), d.get('mueble')))


@api
def instalar(request, taller):
    solo(request, 'POST')
    d = leer_json(request)
    return tarjeta_instalacion(request, *entrega.instalar_leido(request.user, request.taller.slug, texto_de(d),
                                                                proyecto_de(d)))


@api
def desinstalar(request, taller):
    solo(request, 'POST')
    if request.membresia.rol not in GESTION:
        raise Rechazo(403, 'Deshacer una instalación es del dueño o la oficina.')
    d = leer_json(request)
    return responder(200, entrega.desinstalar(request.user, entero(d.get('proyecto')), d.get('mueble')))


@api
def fotos_de_instalacion(request, taller, id):
    """Como las fotos de las tareas (trabajos.api.fotos): el formato real de la imagen, hasta 12 MB."""
    solo(request, 'POST')
    i = entrega.instalacion_o_rechazo(id)
    datos, extension = imagen_del_pedido(request)
    f = entrega.guardar_foto(request.user, request.taller, i, datos, extension)
    return responder(200, {'resultado': 'ok', 'foto': f.pk})


@api
def foto_de_instalacion(request, taller, id):
    solo(request, 'GET')
    f = get_object_or_404(FotoDeInstalacion, pk=id)
    r = abrir_de_taller(request, f.archivo.name)
    r['Cache-Control'] = f'private, max-age={UN_ANIO}, immutable'
    return r


@api
def entrega_visor(request, taller):
    """El paso de cada mueble, para la Lista de entrega y "Colorear por entrega" del visor."""
    solo(request, 'GET')
    p = acciones.proyecto_o_rechazo(entero(request.GET.get('proyecto')))
    piezas = piezas_de(p)
    if not piezas:
        raise Http404()
    d = pasos(p, piezas)
    return responder(200, {'proyecto': acciones.proyecto_a_dic(p), 'muebles': d['muebles'], 'totales': d['totales'],
                           'pasos': [{'clave': k, 'nombre': n, 'color': c} for k, n, c in d['pasos']],
                           'con_control': d['con_control']})


# ---------------------------------------------------------------- ficha 19: anotaciones

@api
def anotar(request, taller):
    solo(request, 'POST')
    d = leer_json(request)
    panel = d.get('panel') if isinstance(d.get('panel'), str) else ''
    return responder(200, entrega.anotar(request.user, request.taller, entero(d.get('proyecto')), d.get('mueble'),
                                         panel, entero(d.get('proceso')), d.get('texto'), d.get('tarea') is True))


def imagen_del_pedido(request):
    """Los bytes de la imagen del cuerpo y su extensión real, como las fotos de las tareas (hasta 12 MB)."""
    tipo = (request.content_type or '').strip().lower()
    if tipo not in TIPOS_FOTO:
        raise Rechazo(415, 'formato de imagen no admitido')
    largo = int(request.META.get('CONTENT_LENGTH') or 0)
    if largo <= 0 or largo > MAX_FOTO:
        raise Rechazo(413, 'imagen vacía o demasiado grande')
    datos = request.read(MAX_FOTO + 1)
    if not datos or len(datos) > MAX_FOTO:
        raise Rechazo(413, 'imagen vacía o demasiado grande')
    return datos, EXTENSION[imagen_valida(datos, tipo)]


@api
def fotos_de_anotacion(request, taller, id):
    solo(request, 'POST')
    a = entrega.anotacion_o_rechazo(id)
    datos, extension = imagen_del_pedido(request)
    f = entrega.guardar_foto_de_anotacion(request.user, request.taller, a, datos, extension)
    return responder(200, {'resultado': 'ok', 'foto': f.pk})


@api
def foto_de_anotacion(request, taller, id):
    solo(request, 'GET')
    f = get_object_or_404(FotoDeAnotacion, pk=id)
    r = abrir_de_taller(request, f.archivo.name)
    r['Cache-Control'] = f'private, max-age={UN_ANIO}, immutable'
    return r


# ---------------------------------------------------------------- ficha 20: avance de un proceso (3D de Mi puesto)

@api
def avance_proceso(request, taller):
    """Qué muebles (y piezas, en un proceso por pieza) cumplieron un proceso: lo que pinta el 3D de Mi puesto."""
    solo(request, 'GET')
    p = acciones.proyecto_o_rechazo(entero(request.GET.get('proyecto')))
    etapa = next((e for e in procesos_del_taller() if e.pk == entero(request.GET.get('proceso'))), None)
    if etapa is None:
        raise Rechazo(404, 'Ese proceso no existe.')
    piezas = piezas_de(p)
    if not piezas:
        raise Http404()
    d = avance_de_proceso(p, etapa, piezas)
    return responder(200, {'proyecto': acciones.proyecto_a_dic(p), 'proceso': {'id': etapa.pk, 'nombre': etapa.nombre},
                           **d, 'colores': COLORES_AVANCE, 'nombres': NOMBRES_AVANCE})


# ---------------------------------------------------------------- ficha 21: carga nueva al escanear y cerrarla

@api
def bulto_carga_nueva(request, taller):
    """El primer bulto de una carga que se crea al escanear (libre: lleva solo lo que se escanee)."""
    solo(request, 'POST')
    return responder(200, acciones.bulto_leido(request.user, request.taller.slug, None, texto_de(leer_json(request))))


@api
def salir_carga(request, taller, id):
    """"Cerrar la carga" en Mi puesto: sale a obra aunque falte algo (queda para otro envío)."""
    solo(request, 'POST')
    d = leer_json(request)
    c = acciones.carga_o_rechazo(id)
    acciones.salir(request.user, c, d.get('motivo'))
    return responder(200, {'resultado': 'ok', 'carga': acciones.carga_a_dic(c)})
