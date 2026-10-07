from django.apps import AppConfig


class ServicioConfig(AppConfig):
    """Lo que necesita el servicio para correr en un servidor: /salud/, latido de la cola y copias de la base.
    No tiene modelos."""
    name = 'servicio'
    verbose_name = 'Servicio'
