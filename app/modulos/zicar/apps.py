from django.apps import AppConfig


class ZicarConfig(AppConfig):
    name = 'modulos.zicar'
    label = 'zicar'
    verbose_name = 'Módulo Zicar'

    def ready(self):
        from . import modulo  # noqa: F401  (registra el módulo)
