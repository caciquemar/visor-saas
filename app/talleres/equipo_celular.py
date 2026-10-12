"""Lo que recuerda cada celular (decisión 2026-10-12): si es propio o del taller, y quiénes entraron en él. Va en
una cookie firmada que dura un año; no guarda contraseñas ni PIN, solo ids de usuario.

- En /entrar/ aparecen como botones los que ya entraron en ese celular (y nadie más: no es una lista pública).
- En un celular propio se ofrece entrar con la huella o el desbloqueo del celular (llaves de acceso, ver
  usuarios/llaves.py); en uno del taller, nunca: ahí cada uno pone su PIN.
"""
import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing

COOKIE = 'visor_celular'
SAL = 'visor.celular'
DURA = 365 * 24 * 3600
MAXIMO = 10
PROPIO, DEL_TALLER = 'propio', 'taller'


def leer(request):
    """{'tipo': 'propio' | 'taller' | None, 'ids': [...]} (vacío si no hay cookie o la tocaron)."""
    try:
        datos = json.loads(request.get_signed_cookie(COOKIE, salt=SAL, max_age=DURA))
        tipo = datos.get('tipo') if datos.get('tipo') in (PROPIO, DEL_TALLER) else None
        ids = [int(i) for i in datos.get('ids', [])][:MAXIMO]
    except (KeyError, ValueError, TypeError, AttributeError, signing.BadSignature):
        return {'tipo': None, 'ids': []}
    return {'tipo': tipo, 'ids': ids}


def guardar(respuesta, datos):
    respuesta.set_signed_cookie(
        COOKIE, json.dumps({'tipo': datos['tipo'], 'ids': datos['ids'][:MAXIMO]}), salt=SAL, max_age=DURA,
        httponly=True, samesite='Lax', secure=not settings.DEBUG)
    return respuesta


def recordar(request, respuesta, usuario, tipo=None):
    """Suma (o sube al principio) a quien acaba de entrar. `tipo` lo fija si se sabe (link de entrada: propio)."""
    datos = leer(request)
    datos['ids'] = [usuario.pk] + [i for i in datos['ids'] if i != usuario.pk]
    if tipo:
        datos['tipo'] = tipo
    return guardar(respuesta, datos)


def elegir_tipo(request, respuesta, tipo):
    datos = leer(request)
    datos['tipo'] = tipo
    return guardar(respuesta, datos)


def olvidar(request, respuesta, usuario_id):
    datos = leer(request)
    datos['ids'] = [i for i in datos['ids'] if i != usuario_id]
    return guardar(respuesta, datos)


def personas(request):
    """Los que entraron en este celular (activos), en orden, para los botones de /entrar/."""
    datos = leer(request)
    if not datos['ids']:
        return []
    Usuario = get_user_model()
    por_id = {u.pk: u for u in Usuario.objects.filter(pk__in=datos['ids'], is_active=True)
              .prefetch_related('llaves')}
    propio = datos['tipo'] == PROPIO
    lista = []
    for i in datos['ids']:
        u = por_id.get(i)
        if u is None:
            continue
        lista.append({'id': u.pk, 'nombre': str(u), 'entra_con': u.email or u.usuario or '',
                      'con_pin': not u.email, 'huella': propio and bool(u.llaves.all())})
    return [x for x in lista if x['entra_con']]
