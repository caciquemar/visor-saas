from django.apps import AppConfig
from django.db.backends.signals import connection_created
from django.db.models.signals import post_migrate, post_save


class TalleresConfig(AppConfig):
    name = 'talleres'
    verbose_name = 'Talleres'

    def ready(self):
        from . import rls
        connection_created.connect(rls.al_conectar, dispatch_uid='visor-rls')
        post_migrate.connect(rls.aplicar_politicas, sender=self, dispatch_uid='visor-rls')
        post_save.connect(roles_del_taller_nuevo, sender='talleres.Taller', dispatch_uid='visor-roles')


def roles_del_taller_nuevo(sender, instance, created, raw=False, **kwargs):
    """Cada taller nuevo arranca con los cuatro roles iniciales (ficha 23)."""
    if created and not raw:
        from .models import crear_roles_iniciales
        crear_roles_iniciales(instance)
