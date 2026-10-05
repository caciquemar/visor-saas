"""Guardianes de las reglas 1 y 2 para las fichas que vienen: fallan si un modelo o una dirección nueva se
saltea la separación entre talleres o el login."""
import re
from pathlib import Path

import pytest
from django.apps import apps
from django.db import models
from django.urls import URLPattern, URLResolver, get_resolver

from talleres.separacion import ARCHIVOS_CON_SIN_FILTRO, DatoDeTaller, PorTaller

APP = Path(__file__).resolve().parents[2] / 'app'

# Modelos de la app que no son datos de un taller (agregar acá solo con una buena razón).
MODELOS_SIN_TALLER = {'talleres.Taller', 'usuarios.Usuario'}

# Direcciones que se pueden ver sin sesión (regla 2). El link del cliente (/c/<código>) se suma en la ficha 04.
PUBLICAS = {'entrar', 'olvide', 'olvide_enviado', 'clave_nueva', 'clave_lista', 'invitacion', 'taller:pin',
            'admin:login'}


def modelos_propios():
    """Modelos de este repo (app/ y tests/), no los de Django ni de otros paquetes."""
    for modelo in apps.get_models():
        ruta = Path(modelo._meta.app_config.path).resolve()
        if ruta.is_relative_to(APP.parent) and '.venv' not in ruta.parts:
            yield modelo


def test_hay_modelos_para_revisar():
    nombres = {m._meta.label for m in modelos_propios()}
    assert {'talleres.Taller', 'talleres.Membresia', 'usuarios.Usuario', 'taller_prueba.Nota'} <= nombres


@pytest.mark.parametrize('modelo', list(modelos_propios()), ids=lambda m: m._meta.label)
def test_todo_modelo_con_datos_de_taller_hereda_de_dato_de_taller(modelo):
    if modelo._meta.label in MODELOS_SIN_TALLER:
        return
    assert issubclass(modelo, DatoDeTaller), (
        f'{modelo._meta.label} no hereda de DatoDeTaller. Si guarda datos de un taller, tiene que heredar; '
        f'si no, agregalo a MODELOS_SIN_TALLER con el motivo.')
    assert isinstance(modelo._default_manager, PorTaller), f'{modelo._meta.label}: el manager por defecto no filtra'
    assert modelo._default_manager.name == 'objects'
    for campo in modelo._meta.many_to_many:
        through = campo.remote_field.through
        assert issubclass(through, DatoDeTaller), (
            f'{modelo._meta.label}.{campo.name}: una relación muchos a muchos entre datos de taller necesita un '
            f'modelo intermedio (through) que herede de DatoDeTaller')


def test_ningun_otro_modelo_tiene_campo_taller():
    for modelo in modelos_propios():
        if not issubclass(modelo, DatoDeTaller):
            assert not any(f.name == 'taller' for f in modelo._meta.get_fields()), modelo._meta.label


def test_sin_filtro_solo_en_los_archivos_permitidos():
    usos = {}
    for archivo in APP.rglob('*.py'):
        relativo = archivo.relative_to(APP).as_posix()
        if '/migrations/' in relativo:
            continue
        texto = archivo.read_text(encoding='utf-8')
        if re.search(r'\bsin_filtro\b|\b_base_manager\b|\.raw\(|connection\.cursor|\bextra\(', texto):
            usos[relativo] = True
    sobran = set(usos) - ARCHIVOS_CON_SIN_FILTRO
    assert not sobran, f'Usan sin_filtro/_base_manager/raw/cursor fuera de lo permitido: {sorted(sobran)}'


def direcciones(patrones=None, prefijo='', espacio=''):
    for p in patrones if patrones is not None else get_resolver().url_patterns:
        ruta = str(p.pattern)
        ruta = re.sub(r'<(?:(\w+):)?(\w+)>', lambda m: {'int': '1', 'path': 'x/y'}.get(m.group(1), 'taller-a')
                      if m.group(2) == 'taller' else {'int': '1', 'path': 'x/y'}.get(m.group(1), 'x'), ruta)
        ruta = re.sub(r'\(\?P<\w+>[^)]*\)', 'usuarios', ruta).lstrip('^').rstrip('$').replace('\\', '')
        if isinstance(p, URLResolver):
            ns = f'{espacio}{p.namespace}:' if p.namespace else espacio
            yield from direcciones(p.url_patterns, prefijo + ruta, ns)
        elif isinstance(p, URLPattern):
            yield f'{espacio}{p.name}', '/' + prefijo + ruta


@pytest.mark.parametrize('nombre,direccion', list(direcciones()))
def test_nada_se_ve_sin_sesion(client, db, nombre, direccion):
    from talleres.models import Taller
    Taller.objects.create(nombre='A', slug='taller-a')
    if nombre in PUBLICAS:
        return
    for metodo in (client.get, client.post):
        r = metodo(direccion)
        assert r.status_code != 200, f'{nombre} ({direccion}) se ve sin sesión'
        if r.status_code in (301, 302):
            assert r['Location'].startswith(('/entrar/', '/admin/')), (nombre, r['Location'])


def test_dato_de_taller_tiene_taller_protegido():
    campo = DatoDeTaller._meta.get_field('taller')
    assert campo.remote_field.on_delete is models.PROTECT       # regla 7: no se borra un taller con datos
    assert not campo.editable and not campo.null
