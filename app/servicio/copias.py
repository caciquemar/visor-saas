"""Copias de la base (PostgreSQL) fuera del servidor: en el almacenamiento `copias` (un bucket de R2 aparte; en la PC,
datos/copias/). Los archivos de los talleres ya están en R2 y no entran acá.

- `hacer_copia()`: pg_dump a `diarias/`; la primera copia de cada mes también a `mensuales/`. Quedan las últimas
  COPIAS_DIARIAS y COPIAS_MENSUALES. La corre todos los días servicio/tareas.py, o a mano `manage.py copia_base`.
- `restaurar()`: baja una copia y la carga con pg_restore, en la base de la app o en una base nueva (para probar la
  copia sin tocar nada). A mano: `manage.py restaurar_copia`. Ver docs/operacion.md.

Las filas se copian como INSERT (no COPY) porque PostgreSQL no deja cargar con COPY tablas con row-level security
(talleres/rls.py); con la variable del taller vacía, la política deja pasar todo.
"""
import os
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.files.storage import storages
from django.utils import timezone

DIARIAS = 'diarias'
MENSUALES = 'mensuales'
TABLAS_PARA_CONTAR = ['usuarios_usuario', 'talleres_taller', 'talleres_membresia', 'proyectos_proyecto',
                      'proyectos_version', 'trabajos_trabajo', 'trabajos_foto']


class ErrorCopia(RuntimeError):
    pass


def almacen():
    return storages['copias']


def conexion():
    """Datos de la base de la app para pg_dump / pg_restore / psql (en variables de entorno, no en la línea)."""
    db = settings.DATABASES['default']
    if db['ENGINE'] != 'django.db.backends.postgresql':
        raise ErrorCopia('Las copias son de PostgreSQL: con SQLite no hay nada que copiar.')
    entorno = {**os.environ, 'PGHOST': db.get('HOST') or 'localhost', 'PGPORT': str(db.get('PORT') or 5432),
               'PGUSER': db.get('USER') or '', 'PGPASSWORD': db.get('PASSWORD') or ''}
    return db['NAME'], entorno


def correr(comando, entorno):
    p = subprocess.run(comando, env=entorno, capture_output=True, text=True)
    if p.returncode != 0:
        raise ErrorCopia(f'{comando[0]} terminó con código {p.returncode}:\n{p.stderr[-4000:]}')
    return p.stdout


def listar(carpeta):
    """Nombres de las copias de la carpeta, de la más vieja a la más nueva."""
    try:
        _, archivos = almacen().listdir(carpeta)
    except FileNotFoundError:
        return []
    return sorted(a for a in archivos if a.endswith('.dump'))


def podar(carpeta, cuantas):
    for nombre in listar(carpeta)[:-cuantas] if cuantas > 0 else []:
        almacen().delete(f'{carpeta}/{nombre}')


def hacer_copia(ahora=None):
    """Hace la copia y devuelve dónde quedó guardada (una o dos rutas)."""
    base, entorno = conexion()
    ahora = timezone.localtime(ahora)
    nombre = f'visor-{ahora:%Y-%m-%d-%H%M}.dump'
    guardadas = []
    with tempfile.TemporaryDirectory(prefix='visor-copia-') as tmp:
        ruta = Path(tmp) / nombre
        correr(['pg_dump', '--format=custom', '--enable-row-security', '--inserts', '--rows-per-insert=500',
                '--file', str(ruta), '--dbname', base], entorno)
        mensual = not any(n.startswith(f'visor-{ahora:%Y-%m}') for n in listar(MENSUALES))
        for carpeta in [DIARIAS] + ([MENSUALES] if mensual else []):
            with open(ruta, 'rb') as f:
                guardadas.append(almacen().save(f'{carpeta}/{nombre}', File(f)))
    podar(DIARIAS, settings.COPIAS_DIARIAS)
    podar(MENSUALES, settings.COPIAS_MENSUALES)
    return guardadas


def contar(base, entorno):
    """Filas de las tablas principales, para comparar una base restaurada con la original."""
    consultas = ' union all '.join(f"select '{t}', count(*) from {t}" for t in TABLAS_PARA_CONTAR)
    salida = correr(['psql', '--no-psqlrc', '-At', '-F', '\t', '--dbname', base, '-c', consultas], entorno)
    return dict((t, int(n)) for t, n in (linea.split('\t') for linea in salida.splitlines() if linea))


def borrar_base(nombre):
    """Borra una base de prueba (la de `restaurar(..., base_nueva=)`). Nunca la de la app."""
    base, entorno = conexion()
    if nombre == base:
        raise ErrorCopia('Esa es la base de la app: no se borra.')
    correr(['dropdb', '--if-exists', '--maintenance-db', base, nombre], entorno)


def restaurar(ruta_copia, base_nueva=None):
    """Carga la copia `ruta_copia` (ej. 'diarias/visor-2026-10-08-0400.dump').

    Sin `base_nueva`: reemplaza la base de la app (borra y vuelve a crear las tablas en una sola transacción).
    Con `base_nueva`: crea esa base y la carga ahí; la de la app no se toca. Devuelve el nombre de la base."""
    base, entorno = conexion()
    destino = base_nueva or base
    with tempfile.TemporaryDirectory(prefix='visor-restaurar-') as tmp:
        local = Path(tmp) / 'copia.dump'
        with almacen().open(ruta_copia, 'rb') as origen, open(local, 'wb') as f:
            while bloque := origen.read(1024 * 1024):
                f.write(bloque)
        if base_nueva:
            correr(['createdb', '--maintenance-db', base, base_nueva], entorno)
        comando = ['pg_restore', '--no-owner', '--no-privileges', '--exit-on-error', '--single-transaction',
                   '--dbname', destino]
        if not base_nueva:
            comando += ['--clean', '--if-exists']
        correr(comando + [str(local)], entorno)
    return destino
