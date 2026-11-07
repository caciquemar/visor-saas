"""La configuración del cobro (models.Cobro), leída una vez por minuto como mucho (en la caché; se borra al guardar).
Si todavía no existe, se crea con los valores del .env."""
from django.conf import settings
from django.core.cache import cache

CLAVE = 'config-cobro'


def olvidar():
    cache.delete(CLAVE)


def cobro():
    from .models import Cobro
    c = cache.get(CLAVE)
    if c is None:
        c = Cobro.objects.filter(pk=1).first()
        if c is None:
            c = Cobro(pk=1, activo=settings.SUSCRIPCIONES_ACTIVAS, pasarela=settings.PASARELA,
                      ambiente=settings.PAYWAY_AMBIENTE, sitio=settings.PAYWAY_SITIO,
                      establecimiento=settings.PAYWAY_ESTABLECIMIENTO, cuit=settings.PAYWAY_CUIT,
                      clave_publica=settings.PAYWAY_CLAVE_PUBLICA)
            c.save()
        cache.set(CLAVE, c, timeout=60)
    return c


def cobro_activo():
    return cobro().activo


def nombre_de_pasarela():
    """La pasarela que se usa. La simulada solo en la PC (DEBUG=1): en el servidor sería aprobar pagos sin pagar."""
    nombre = cobro().pasarela
    if nombre == 'simulada' and not settings.PASARELA_SIMULADA_PERMITIDA:
        return 'payway'
    return nombre
