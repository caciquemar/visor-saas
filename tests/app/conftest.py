"""Dos talleres, A y B, cada uno con su dueño y una nota. Las pruebas intentan cruzar de uno al otro."""
from types import SimpleNamespace

import pytest
from django.core.cache import cache

from talleres.models import Taller
from talleres.separacion import con_taller
from tests.app.ayudas import CLAVE, sumar
from tests.app.taller_prueba.models import Nota


@pytest.fixture(autouse=True)
def cache_limpia():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def archivos_en_carpeta_temporal(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / 'archivos'


@pytest.fixture
def t(db, django_user_model):
    """Talleres A y B con datos. `t.dueno_a` es dueño de A, `t.armador_a` entra con PIN 1234 en A, etc."""
    crear = django_user_model.objects.create_user
    A = Taller.objects.create(nombre='Taller A', slug='taller-a')
    B = Taller.objects.create(nombre='Taller B', slug='taller-b')
    d = SimpleNamespace(A=A, B=B)
    d.dueno_a = crear('dueno@a.com', CLAVE, nombre='Ana')
    d.dueno_b = crear('dueno@b.com', CLAVE, nombre='Beto')
    d.oficina_a = crear('oficina@a.com', CLAVE, nombre='Olga')
    d.armador_a = crear(None, nombre='Arturo')
    d.armador_b = crear(None, nombre='Bruno')
    d.m_dueno_a = sumar(d.dueno_a, A, 'dueno')
    d.m_dueno_b = sumar(d.dueno_b, B, 'dueno')
    d.m_oficina_a = sumar(d.oficina_a, A, 'oficina')
    d.m_armador_a = sumar(d.armador_a, A, 'armador', pin='1234')
    d.m_armador_b = sumar(d.armador_b, B, 'armador', pin='1234')
    with con_taller(A):
        d.nota_a = Nota.objects.create(texto='nota de A')
    with con_taller(B):
        d.nota_b = Nota.objects.create(texto='nota de B')
        d.respuesta_b = Nota.objects.create(texto='respuesta en B', padre=d.nota_b)
    return d


@pytest.fixture
def cliente_de(client):
    """cliente_de(usuario): cliente con la sesión de ese usuario (mail y contraseña, no PIN)."""
    def hacer(usuario):
        client.force_login(usuario)
        return client
    return hacer
