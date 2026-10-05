from talleres.models import Membresia
from talleres.pin import asignar_pin
from talleres.separacion import con_taller

CLAVE = 'una-clave-larga-de-prueba'


def sumar(usuario, taller, rol, pin=None):
    """Suma al usuario al taller con ese rol (y PIN, si se da)."""
    with con_taller(taller):
        m = Membresia.objects.create(usuario=usuario, rol=rol)
        if pin:
            asignar_pin(m, pin)
    return m
