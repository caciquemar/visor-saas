"""Dólar oficial del día: la API de estadísticas del BCRA, variable 4 (tipo de cambio minorista, promedio vendedor).
Si no responde, sigue valiendo la última cotización guardada (y Martín puede cargar una a mano)."""
import logging
from datetime import date, timedelta
from decimal import Decimal

import requests

from .models import Cotizacion

log = logging.getLogger('visor.suscripciones')

URL_BCRA = 'https://api.bcra.gob.ar/estadisticas/v4.0/monetarias/4'


def leer_bcra(hoy):
    """(fecha, pesos por dólar) del último día publicado en los últimos 10, o None."""
    r = requests.get(URL_BCRA, params={'desde': (hoy - timedelta(days=10)).isoformat(), 'hasta': hoy.isoformat()},
                     timeout=20)
    r.raise_for_status()
    detalle = [d for x in r.json().get('results', []) for d in x.get('detalle', [])]
    if not detalle:
        return None
    ultimo = max(detalle, key=lambda d: d['fecha'])
    return date.fromisoformat(ultimo['fecha']), Decimal(str(ultimo['valor'])).quantize(Decimal('0.01'))


def actualizar(hoy):
    try:
        leido = leer_bcra(hoy)
    except Exception:
        log.exception('No se pudo leer la cotización del BCRA; sigue la última guardada')
        return None
    if leido is None:
        return None
    fecha, valor = leido
    c, _ = Cotizacion.objects.get_or_create(fecha=fecha, fuente=Cotizacion.Fuente.BCRA,
                                            defaults={'ars_por_usd': valor})
    return c
