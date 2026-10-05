"""La app levanta: administración de Django, configuración del servidor y cola de tareas."""
import os
import secrets
import subprocess
import sys
from pathlib import Path

from huey.contrib.djhuey import task

RAIZ = Path(__file__).resolve().parents[2]


def test_admin_pide_login(client):
    r = client.get('/admin/')
    assert r.status_code == 302
    assert r['Location'].startswith('/admin/login/')


def test_pagina_de_login_en_castellano(client):
    r = client.get('/admin/login/')
    assert r.status_code == 200
    assert 'Visor' in r.text and 'Contraseña' in r.text


def test_superusuario_entra_a_la_administracion(admin_client):
    r = admin_client.get('/admin/')
    assert r.status_code == 200
    assert 'Usuarios' in r.text


@task()
def sumar(a, b):
    return a + b


def test_cola_en_modo_inmediato():
    assert sumar(2, 3)() == 5


def test_configuracion_de_servidor_sin_errores():
    """manage.py check --deploy con la configuración de producción (DEBUG apagado, R2)."""
    env = {**os.environ, 'DEBUG': '0', 'SECRET_KEY': secrets.token_urlsafe(50), 'ALLOWED_HOSTS': 'visor.ejemplo',
           'ALMACENAMIENTO': 'r2', 'R2_BUCKET': 'b', 'R2_ACCOUNT_ID': 'c', 'R2_ACCESS_KEY_ID': 'k',
           'R2_SECRET_ACCESS_KEY': 's', 'DATABASE_URL': 'sqlite:///:memory:', 'HUEY_INMEDIATO': '0',
           'DJANGO_SETTINGS_MODULE': 'config.settings'}
    p = subprocess.run([sys.executable, str(RAIZ / 'app' / 'manage.py'), 'check', '--deploy', '--fail-level', 'ERROR'],
                       env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    assert p.returncode == 0, p.stdout + p.stderr


def test_almacenamiento_r2_apunta_a_cloudflare():
    env = {**os.environ, 'DEBUG': '1', 'ALMACENAMIENTO': 'r2', 'R2_BUCKET': 'archivos', 'R2_ACCOUNT_ID': 'cuenta',
           'R2_ACCESS_KEY_ID': 'k', 'R2_SECRET_ACCESS_KEY': 's', 'DJANGO_SETTINGS_MODULE': 'config.settings'}
    codigo = ('import django; django.setup(); from django.core.files.storage import default_storage as d; '
              'print(type(d._wrapped if hasattr(d, "_wrapped") else d).__name__, d.endpoint_url, d.bucket_name)')
    p = subprocess.run([sys.executable, '-c', codigo], cwd=RAIZ / 'app', env=env,
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    assert p.returncode == 0, p.stderr
    assert 'https://cuenta.r2.cloudflarestorage.com archivos' in p.stdout
