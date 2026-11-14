"""Ficha 24: proyectos de Fusion. Se sube solo el DXF, se eligen los materiales en la sección Versiones y se vuelve
a convertir. Corre el conversor de verdad con el sillón de muestras/ (tarda un par de segundos)."""
import json

import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile

from proyectos.models import Material, Proyecto, Version
from talleres.separacion import con_taller
from tests.app.ayudas import MUESTRAS, subir

SILLON = MUESTRAS / 'fusion sillon exterior' / 'sillon exterior 2m.dxf'


@pytest.fixture
def dueno_a(cliente_de, t, django_capture_on_commit_callbacks):
    c = cliente_de(t.dueno_a)
    original = c.post

    def post(*args, **kwargs):
        with django_capture_on_commit_callbacks(execute=True):
            return original(*args, **kwargs)
    c.post = post
    return c


def solo_dxf(ruta=SILLON):
    return [SimpleUploadedFile(ruta.name, ruta.read_bytes())]


def proyecto_de(t):
    with con_taller(t.A):
        return Proyecto.objects.select_related('version_actual').get()


def datos_de(version):
    with default_storage.open(version.archivo_proyecto) as f:
        return json.load(f)


def test_se_sube_solo_el_dxf_de_fusion(dueno_a, t):
    r = subir(dueno_a, 'taller-a', lista=solo_dxf())
    assert r.status_code == 302
    p = proyecto_de(t)
    v = p.version_actual
    assert p.nombre == 'sillon exterior 2m' and v.estado == Version.Estado.LISTO, v.mensaje
    assert v.resumen['paneles'] == 19
    assert {g['nombre'] for g in v.resumen['fusion']['grupos']} == {
        'almohadones', 'Component16', 'parrillarespaldo', 'pata', 'respaldo', 'viga'}
    pagina = dueno_a.get(f'/taller-a/proyectos/{p.pk}/?ver=versiones').content.decode()
    assert 'Materiales de Fusion' in pagina and 'De Fusion · 19 piezas' in pagina


def test_un_dxf_de_polyboard_sin_ocp_no_se_acepta(dueno_a, t):
    r = subir(dueno_a, 'taller-a', lista=solo_dxf(MUESTRAS / 'Kogan' / 'Kogan.dxf'))
    assert r.status_code == 400 and 'Falta la lista de OptiCut' in r.content.decode()


def test_elegir_materiales_vuelve_a_convertir_con_ellos(dueno_a, t):
    subir(dueno_a, 'taller-a', lista=solo_dxf())
    with con_taller(t.A):
        Material.objects.create(nombre='Eucalipto', color='#B07A4F')
        Material.objects.create(nombre='Pino', color='#DAB97F')
    p = proyecto_de(t)
    grupos = [g['nombre'] for g in p.version_actual.resumen['fusion']['grupos']]
    eleccion = {'almohadones': '-', 'Component16': 'Pino'}
    datos = {'todo': 'Eucalipto', 'arriba': 'y',
             **{f'pieza_{i}': eleccion.get(n, '') for i, n in enumerate(grupos)}}
    r = dueno_a.post(f'/taller-a/proyectos/{p.pk}/fusion/', datos)
    assert r.status_code == 302
    p = proyecto_de(t)
    assert p.fusion == {'todo': 'Eucalipto', 'arriba': 'y', 'piezas': eleccion}
    v = p.version_actual
    assert v.numero == 2 and v.estado == Version.Estado.LISTO, v.mensaje
    assert v.resumen['paneles'] == 17 and v.resumen['herrajes'] == 2
    mats = {(x['nombre'], x['mat']) for x in datos_de(v)['paneles']}
    assert ('Component16', 'Pino') in mats and ('pata', 'Eucalipto') in mats
    assert not any(n == 'almohadones' for n, _ in mats)
    # la versión nueva que se suba después usa los mismos materiales
    dueno_a.post(f'/taller-a/proyectos/{p.pk}/versiones/nueva/', {'archivos': solo_dxf()})
    assert proyecto_de(t).version_actual.resumen['paneles'] == 17


def test_materiales_de_fusion_solo_quien_gestiona_y_solo_su_taller(dueno_a, cliente_de, t):
    subir(dueno_a, 'taller-a', lista=solo_dxf())
    p = proyecto_de(t)
    armador = cliente_de(t.armador_a)
    assert armador.post(f'/taller-a/proyectos/{p.pk}/fusion/', {'arriba': 'y'}).status_code == 403
    otro = cliente_de(t.dueno_b)
    assert otro.post(f'/taller-b/proyectos/{p.pk}/fusion/', {'arriba': 'y'}).status_code == 404
    assert proyecto_de(t).fusion == {}


def test_un_proyecto_de_polyboard_no_tiene_materiales_de_fusion(dueno_a, t, monkeypatch):
    from proyectos import tareas
    from tests.app.ayudas import CorrerFalso
    monkeypatch.setattr(tareas, 'correr', CorrerFalso())
    subir(dueno_a, 'taller-a')
    p = proyecto_de(t)
    assert 'Materiales de Fusion' not in dueno_a.get(f'/taller-a/proyectos/{p.pk}/?ver=versiones').content.decode()
    assert dueno_a.post(f'/taller-a/proyectos/{p.pk}/fusion/', {'arriba': 'y'}).status_code == 404
