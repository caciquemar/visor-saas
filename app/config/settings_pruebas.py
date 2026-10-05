"""Configuración para pytest: no depende del .env de cada PC (lo que se fija acá le gana al .env)."""
import os

os.environ.update(
    SECRET_KEY='clave-de-pruebas',
    DEBUG='1',
    HUEY_INMEDIATO='1',
    ALMACENAMIENTO='local',
    DATABASE_URL='sqlite://:memory:',
    REDIS_URL='',
    DOMINIO_APP='testserver',
    EMAIL_URL='',
)

from .settings import *  # noqa: E402,F401,F403

# App con un modelo de prueba (Nota) para probar la separación entre talleres antes de que existan
# proyectos y trabajos. Solo existe en las pruebas.
INSTALLED_APPS = [*INSTALLED_APPS, 'tests.app.taller_prueba']  # noqa: F405
ROOT_URLCONF = 'tests.app.taller_prueba.urls'
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']   # pruebas más rápidas
