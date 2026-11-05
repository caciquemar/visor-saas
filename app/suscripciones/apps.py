from django.apps import AppConfig
from django.db.models.signals import post_save


class SuscripcionesConfig(AppConfig):
    name = 'suscripciones'
    verbose_name = 'Suscripciones'

    def ready(self):
        post_save.connect(suscripcion_del_taller_nuevo, sender='talleres.Taller', dispatch_uid='visor-suscripcion')


def suscripcion_del_taller_nuevo(sender, instance, created, raw=False, **kwargs):
    """Cada taller nuevo arranca en prueba (ficha 08)."""
    if created and not raw:
        from .servicio import crear_suscripcion
        crear_suscripcion(instance)
