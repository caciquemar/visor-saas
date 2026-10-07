from django.core.management.base import BaseCommand, CommandError

from servicio import copias


class Command(BaseCommand):
    help = 'Hace ahora una copia de la base y la guarda en el almacenamiento de copias (la misma que la diaria).'

    def handle(self, *args, **opciones):
        try:
            guardadas = copias.hacer_copia()
        except copias.ErrorCopia as e:
            raise CommandError(str(e))
        for nombre in guardadas:
            self.stdout.write(f'Copia guardada: {nombre}')
