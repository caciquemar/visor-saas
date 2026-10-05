"""PIN de armadores e instaladores para el celular compartido del taller.

Se puede usar desde cualquier celular (decisión 2026-10-05), así que el bloqueo es duro:
- cada 5 fallos seguidos de una persona: 15 minutos sin poder probar;
- a los 10 fallos seguidos: bloqueado hasta que el dueño u oficina lo desbloquee en Equipo;
- además, por IP y taller: 20 fallos en una hora y esa IP no puede probar más por una hora.
Con un PIN de 4 dígitos, alguien de afuera tiene como mucho 10 intentos sobre 10.000 por persona.
"""
import re
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db.models import F
from django.utils import timezone

SESION_PIN = 'pin_taller'          # en la sesión: id del taller donde se entró con PIN
HORAS_SESION_PIN = 12
FALLOS_PAUSA = 5
MINUTOS_PAUSA = 15
FALLOS_BLOQUEO = 10
FALLOS_POR_IP = 20


class PinBloqueado(Exception):
    pass


def validar_pin(pin):
    if not re.fullmatch(r'\d{4,6}', pin or ''):
        raise ValidationError('El PIN tiene que ser de 4 a 6 números.')


def asignar_pin(membresia, pin):
    validar_pin(pin)
    membresia.pin = make_password(pin)
    membresia.pin_fallos = 0
    membresia.pin_bloqueado_hasta = None
    membresia.save(update_fields=['pin', 'pin_fallos', 'pin_bloqueado_hasta'])


def desbloquear(membresia):
    membresia.pin_fallos = 0
    membresia.pin_bloqueado_hasta = None
    membresia.save(update_fields=['pin_fallos', 'pin_bloqueado_hasta'])


def bloqueado_del_todo(membresia):
    return membresia.pin_fallos >= FALLOS_BLOQUEO


def _clave_ip(taller, ip):
    return f'pin-fallos:{taller.pk}:{ip}'


def probar_pin(membresia, pin, ip):
    """True si el PIN es correcto. Lanza PinBloqueado si no se puede probar ahora."""
    ahora = timezone.now()
    clave = _clave_ip(membresia.taller, ip)
    if cache.get(clave, 0) >= FALLOS_POR_IP:
        raise PinBloqueado('Demasiados intentos desde este celular. Probá de nuevo en una hora.')
    if bloqueado_del_todo(membresia):
        raise PinBloqueado('PIN bloqueado. Pedile al dueño o a la oficina que lo desbloquee.')
    if membresia.pin_bloqueado_hasta and ahora < membresia.pin_bloqueado_hasta:
        raise PinBloqueado(f'Demasiados intentos. Probá de nuevo en {MINUTOS_PAUSA} minutos.')

    if membresia.pin and check_password(pin, membresia.pin):
        if membresia.pin_fallos or membresia.pin_bloqueado_hasta:
            desbloquear(membresia)
        return True

    type(membresia).objects.filter(pk=membresia.pk).update(pin_fallos=F('pin_fallos') + 1)
    membresia.refresh_from_db(fields=['pin_fallos'])
    if membresia.pin_fallos % FALLOS_PAUSA == 0 and not bloqueado_del_todo(membresia):
        membresia.pin_bloqueado_hasta = ahora + timedelta(minutes=MINUTOS_PAUSA)
        membresia.save(update_fields=['pin_bloqueado_hasta'])
    cache.add(clave, 0, timeout=3600)
    try:
        cache.incr(clave)
    except ValueError:                    # venció justo entre add e incr
        cache.set(clave, 1, timeout=3600)
    return False
