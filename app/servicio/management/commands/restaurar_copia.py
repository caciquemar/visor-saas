from django.core.management.base import BaseCommand, CommandError

from servicio import copias


class Command(BaseCommand):
    help = ('Sin nada: lista las copias. Con una copia y --base: la carga en una base nueva para probarla (no toca '
            'la de la app). Con una copia y --si: reemplaza la base de la app por la copia. Ver docs/operacion.md.')

    def add_arguments(self, parser):
        parser.add_argument('copia', nargs='?', help='ej. diarias/visor-2026-10-08-0400.dump')
        parser.add_argument('--base', help='base nueva donde cargarla (ej. prueba_copia); se crea')
        parser.add_argument('--si', action='store_true', help='confirmar que se reemplaza la base de la app')
        parser.add_argument('--borrar-base', metavar='BASE', help='borrar una base de prueba creada con --base')

    def handle(self, *args, copia=None, base=None, si=False, borrar_base=None, **opciones):
        if borrar_base:
            try:
                copias.borrar_base(borrar_base)
            except copias.ErrorCopia as e:
                raise CommandError(str(e))
            self.stdout.write(f'Base {borrar_base} borrada.')
            return
        if not copia:
            for carpeta in (copias.DIARIAS, copias.MENSUALES):
                for nombre in copias.listar(carpeta):
                    self.stdout.write(f'{carpeta}/{nombre}')
            return
        if not base and not si:
            raise CommandError('Esto reemplaza la base de la app por la copia. Para seguir, agregá --si '
                               '(o usá --base <nombre> para cargarla en una base aparte).')
        try:
            destino = copias.restaurar(copia, base_nueva=base)
            original, entorno = copias.conexion()
            self.stdout.write(f'Copia {copia} cargada en la base {destino}. Filas por tabla:')
            cuentas = copias.contar(destino, entorno)
            comparar = copias.contar(original, entorno) if base else {}
        except copias.ErrorCopia as e:
            raise CommandError(str(e))
        for tabla, n in cuentas.items():
            extra = f'   (en la base de la app: {comparar[tabla]})' if base else ''
            self.stdout.write(f'  {tabla:<22} {n:>7}{extra}')
