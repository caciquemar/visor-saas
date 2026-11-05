"""Procesador de contexto: el aviso de arriba de las páginas del taller (prueba por vencer, vencida, solo lectura)."""
from django.urls import reverse

from . import estados
from .servicio import hoy


def aviso(request):
    s, e = getattr(request, 'suscripcion', None), getattr(request, 'estado_suscripcion', None)
    if s is None or getattr(request, 'membresia', None) is None:
        return {}
    hasta = estados.cubierto_hasta(s)
    faltan = (hasta - hoy()).days
    if e == estados.PRUEBA and faltan > 7:
        return {}
    if e == estados.ACTIVA and (faltan > 7 or s.sin_cobro_hasta and s.sin_cobro_hasta >= hoy()):
        return {}
    textos = {
        estados.PRUEBA: f'La prueba termina el {hasta:%d/%m/%Y}.',
        estados.ACTIVA: f'Tu plan vence el {hasta:%d/%m/%Y}.',
        estados.VENCIDA: f'Tu plan venció el {hasta:%d/%m/%Y}. En unos días la cuenta queda en solo lectura.',
        estados.SOLO_LECTURA: 'La cuenta está en solo lectura: se ve todo, pero no se puede cambiar nada.',
    }
    if e not in textos:
        return {}
    url = (reverse('taller:suscripcion:pantalla', kwargs={'taller': request.taller.slug})
           if request.membresia.puede('suscripcion') else None)
    return {'aviso_suscripcion': {'texto': textos[e], 'url': url, 'grave': e in (estados.VENCIDA, estados.SOLO_LECTURA)}}
