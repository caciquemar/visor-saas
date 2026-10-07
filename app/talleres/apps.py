from django.apps import AppConfig
from django.db.backends.signals import connection_created
from django.db.models.signals import post_migrate


class TalleresConfig(AppConfig):
    name = 'talleres'
    verbose_name = 'Talleres'

    def ready(self):
        from . import rls
        connection_created.connect(rls.al_conectar, dispatch_uid='visor-rls')
        post_migrate.connect(rls.aplicar_politicas, sender=self, dispatch_uid='visor-rls')
