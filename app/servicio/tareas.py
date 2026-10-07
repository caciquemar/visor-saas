"""Tareas periódicas del servicio (las corre el consumidor de Huey; en la PC, con HUEY_INMEDIATO=1, no corren)."""
import logging
import time

from django.core.cache import cache
from huey import crontab
from huey.contrib.djhuey import db_periodic_task, periodic_task

from . import copias

log = logging.getLogger('visor.servicio')

LATIDO = 'latido-cola'          # en la caché: cuándo fue el último latido del consumidor (lo mira /salud/)


@periodic_task(crontab(minute='*'))
def latido():
    cache.set(LATIDO, time.time(), timeout=24 * 3600)


# Huey va en UTC (settings.HUEY['utc']): 7 UTC = 4 de la mañana en la Argentina.
@db_periodic_task(crontab(hour='7', minute='0'), retries=2, retry_delay=15 * 60)
def copia_diaria():
    for nombre in copias.hacer_copia():
        log.info('Copia de la base guardada: %s', nombre)
