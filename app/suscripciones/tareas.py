"""Revisión diaria (la corre el consumidor de Huey; en la PC, `manage.py revisar_suscripciones`): cotización del
dólar, pagos que no avisaron, estado de cada taller y mails."""
import logging

from huey import crontab
from huey.contrib.djhuey import db_periodic_task

from talleres.models import Taller

from . import cotizacion
from .servicio import hoy, revisar_taller

log = logging.getLogger('visor.suscripciones')


def revisar_todo(dia=None):
    dia = dia or hoy()
    cotizacion.actualizar(dia)
    for taller in Taller.objects.filter(activo=True):
        try:
            revisar_taller(taller, dia)
        except Exception:
            log.exception('No se pudo revisar la suscripción de %s', taller)


# Huey va en UTC: 10 UTC = 7 de la mañana en la Argentina.
@db_periodic_task(crontab(hour='10', minute='0'), retries=2, retry_delay=15 * 60)
def revision_diaria():
    revisar_todo()
