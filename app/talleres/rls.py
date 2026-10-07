"""Segunda barrera entre talleres, en PostgreSQL (row-level security). La primera es talleres/separacion.py.

- Después de cada `migrate`, toda tabla de un modelo `DatoDeTaller` queda con RLS forzada (vale también para el
  dueño de la tabla) y la política `por_taller`: con la variable `visor.taller` puesta, la base solo deja leer y
  escribir filas de ese taller. Un modelo nuevo la recibe solo, al migrar.
- Antes de cada consulta se pone `visor.taller` con el taller del contexto (`taller_actual`, el mismo que usa la
  primera barrera). Sin taller en el contexto (administración, entrar, el middleware antes de saber el taller,
  migraciones, copias) la variable queda vacía y la base no filtra: ahí manda la primera barrera.
  O sea: dentro de un pedido o una tarea de un taller, aunque el código tuviera un error, la base no devuelve ni
  cambia datos de otro.
- No vale para un superusuario de PostgreSQL: la app tiene que entrar con un usuario común (ver despliegue/).
- En SQLite (la PC y las pruebas rápidas) no hace nada.
"""
from django.apps import apps
from django.db import connections
from psycopg.pq import TransactionStatus

from .separacion import DatoDeTaller, taller_actual

POLITICA = 'por_taller'
_TALLER = "nullif(current_setting('visor.taller', true), '')"
CONDICION = f'{_TALLER} is null or taller_id = {_TALLER}::bigint'


def tablas_de_taller():
    return sorted({m._meta.db_table for m in apps.get_models()
                   if issubclass(m, DatoDeTaller) and m._meta.managed and not m._meta.proxy})


def aplicar_politicas(using='default', **_):
    """Se llama después de cada migrate (post_migrate). Se puede repetir: rehace la política de cada tabla."""
    conexion = connections[using]
    if conexion.vendor != 'postgresql':
        return
    qn = conexion.ops.quote_name
    with conexion.cursor() as c:
        for tabla in tablas_de_taller():
            c.execute(f'alter table {qn(tabla)} enable row level security')
            c.execute(f'alter table {qn(tabla)} force row level security')
            c.execute(f'drop policy if exists {POLITICA} on {qn(tabla)}')
            c.execute(f'create policy {POLITICA} on {qn(tabla)} using ({CONDICION}) with check ({CONDICION})')


def poner_taller(execute, sql, params, many, context):
    """execute_wrapper de Django: deja `visor.taller` igual al taller del contexto antes de la consulta.

    Fuera de una transacción el valor queda en la conexión y solo se vuelve a poner si cambia. Dentro de una
    transacción se pone siempre, porque si la transacción se deshace, el valor también vuelve atrás."""
    conexion = context['connection']
    if conexion.connection.info.transaction_status == TransactionStatus.INERROR:
        # Transacción con error: PostgreSQL solo acepta el ROLLBACK (o volver a un savepoint) que viene ahora.
        return execute(sql, params, many, context)
    taller = taller_actual.get()
    valor = str(taller.pk) if taller is not None and taller.pk is not None else ''
    if conexion.in_atomic_block or getattr(conexion, '_visor_taller', None) != valor:
        context['cursor'].cursor.execute("select set_config('visor.taller', %s, false)", [valor])
        conexion._visor_taller = None if conexion.in_atomic_block else valor
    return execute(sql, params, many, context)


def al_conectar(sender, connection, **_):
    """Señal connection_created: cada conexión nueva a PostgreSQL pasa por poner_taller."""
    if connection.vendor != 'postgresql':
        return
    connection._visor_taller = None
    if poner_taller not in connection.execute_wrappers:
        connection.execute_wrappers.append(poner_taller)
