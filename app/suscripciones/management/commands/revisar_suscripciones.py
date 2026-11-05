from django.core.management.base import BaseCommand

from suscripciones.tareas import revisar_todo


class Command(BaseCommand):
    help = 'Revisión diaria de las suscripciones: cotización, pagos pendientes, estados y avisos por mail.'

    def handle(self, *args, **opciones):
        revisar_todo()
        self.stdout.write('Listo.')
