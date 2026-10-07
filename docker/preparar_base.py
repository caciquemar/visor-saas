"""Deja lista la base de PostgreSQL para la app (servicio `preparar` del compose, corre una vez en cada arranque).

Con el superusuario (`postgres`, clave POSTGRES_PASSWORD) crea el usuario y la base de DATABASE_URL si no existen, y
le pone la clave de DATABASE_URL. El usuario de la app NO es superusuario: así PostgreSQL le aplica la row-level
security entre talleres (app/talleres/rls.py). Puede crear bases (para probar copias en una base aparte).
Solo este servicio conoce la clave del superusuario; la app no.
"""
import os
import sys
import time
from urllib.parse import unquote, urlparse

import psycopg
from psycopg import sql


def main():
    url = urlparse(os.environ['DATABASE_URL'])
    usuario, clave, base = unquote(url.username), unquote(url.password or ''), url.path.lstrip('/')
    datos = dict(host=url.hostname, port=url.port or 5432, user='postgres',
                 password=os.environ['POSTGRES_PASSWORD'], dbname='postgres', autocommit=True)
    for intento in range(60):
        try:
            cx = psycopg.connect(**datos)
            break
        except psycopg.OperationalError:
            print('Esperando a PostgreSQL...', flush=True)
            time.sleep(2)
    else:
        sys.exit('PostgreSQL no respondió en 2 minutos')
    with cx:
        existe = cx.execute('select 1 from pg_roles where rolname = %s', [usuario]).fetchone()
        accion = 'alter' if existe else 'create'
        cx.execute(sql.SQL(f'{accion} role {{}} login nosuperuser nobypassrls createdb password {{}}').format(
            sql.Identifier(usuario), sql.Literal(clave)))
        if not cx.execute('select 1 from pg_database where datname = %s', [base]).fetchone():
            cx.execute(sql.SQL('create database {} owner {}').format(sql.Identifier(base), sql.Identifier(usuario)))
            print(f'Base {base} creada', flush=True)
    print(f'Base {base} lista para el usuario {usuario}', flush=True)


if __name__ == '__main__':
    main()
