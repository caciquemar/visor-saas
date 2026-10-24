"""API del puesto (/<taller>/puesto/api/…) y del avance en el visor (/<taller>/visor/api/avance). Cualquier miembro
del taller; reabrir un mueble es del dueño o la oficina. Como en el resto de la app, el filtro por taller lo pone
DatoDeTaller: ids y códigos de otro taller no se encuentran.

    POST puesto/api/marcar                 {texto, etapa, proyecto?, ubicacion?}   pieza en una etapa (y lugar)
    POST puesto/api/deshacer               {marca}
    POST puesto/api/mueble                 {texto, proyecto?}          qué mueble es y cuánto le falta
    GET  puesto/api/mueble?proyecto=&mueble=
    POST puesto/api/terminar               {proyecto, mueble, bultos, motivo, ubicacion?}
    POST puesto/api/tareas                 {texto, proyecto?}          tareas sin instalar de una pieza o mueble
    POST puesto/api/reabrir                {proyecto, mueble}
    GET  puesto/api/cargas/<id>
    POST puesto/api/cargas/<id>/bulto      {texto, entregar?}
    POST puesto/api/cargas/<id>/deshacer   {bulto}
    GET  visor/api/avance?proyecto=<id>
"""
from django.http import Http404

from talleres.roles import Rol
from trabajos.api import Rechazo, api, leer_json, responder, solo, uno

from . import acciones
from .calculo import avance, piezas_de, piezas_nuevas

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
    solo(request, 'POST')
    return responder(200, acciones.deshacer(request.user, entero(leer_json(request).get('marca'))))


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
    return responder(200, acciones.bulto_leido(request.user, request.taller.slug, id, texto_de(d),
                                               entregar=d.get('entregar') is True))


@api
def deshacer_bulto(request, taller, id):
    solo(request, 'POST')
    return responder(200, acciones.deshacer_bulto(request.user, id, entero(leer_json(request).get('bulto'))))


@api
def avance_visor(request, taller):
    """Para el visor: por panel, las etapas hechas; por mueble, el % y si está terminado; las piezas nuevas de la
    versión. `final` es la etapa de armado (las piezas que la tienen se pintan con otro tono)."""
    solo(request, 'GET')
    p = acciones.proyecto_o_rechazo(entero(request.GET.get('proyecto')))
    piezas = piezas_de(p)
    if not piezas:
        raise Http404()
    a = avance(p, piezas)
    armado = acciones.etapa_de_armado()
    return responder(200, {
        'etapas': [{'id': e.pk, 'nombre': e.nombre} for e in a['etapas']],
        'final': armado.pk if armado else None,
        'pct': a['total']['pct'],
        'paneles': a['paneles'],
        'muebles': {n: {'pct': m['pct'], 'piezas': m['piezas'],
                        'por_etapa': [m['por_etapa'][e.pk] for e in a['etapas']],
                        'terminado': bool(m['fin'])} for n, m in a['muebles'].items()},
        'nuevas': [x['panel']['id'] for x in piezas_nuevas(p, piezas)],
    })
