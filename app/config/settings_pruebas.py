"""Configuración para pytest: no depende del .env de cada PC (lo que se fija acá le gana al .env)."""
import os

os.environ.update(
    SECRET_KEY='clave-de-pruebas',
    DEBUG='1',
    HUEY_INMEDIATO='1',
    ALMACENAMIENTO='local',
    DATABASE_URL='sqlite://:memory:',
    REDIS_URL='',
)

from .settings import *  # noqa: E402,F401,F403
