"""Proyectos de Fusion (ficha 24): el DXF solo, con los materiales elegidos en el visor."""
import json
from pathlib import Path

import pytest

from conversor import ErrorConversion, convertir
from conversor.fusion import base, es_de_fusion, leer_fusion
from conversor.polyboard_a_app import bbox

MUESTRAS = Path(__file__).resolve().parents[2] / 'muestras'
SILLON = MUESTRAS / 'fusion sillon exterior' / 'sillon exterior 2m.dxf'


def test_reconoce_el_dxf_de_fusion():
    assert es_de_fusion(SILLON)
    assert not es_de_fusion(MUESTRAS / 'Kogan' / 'Kogan.dxf')
    with open(SILLON, 'rb') as f:          # también un archivo abierto (la subida), que queda al principio
        assert es_de_fusion(f) and f.tell() == 0


def test_nombre_sin_el_numero_de_copia():
    assert base('pata(3)') == 'pata'
    assert base('pata (12)') == 'pata'
    assert base('Component16') == 'Component16'


def test_lee_todos_los_solidos_parados():
    """Los 19 cuerpos, también el almohadón con el transform nuevo; Y arriba en Fusion pasa a Z arriba."""
    solidos, _, fallidos = leer_fusion(SILLON)
    assert len(solidos) == 19 and not fallidos
    pata = next(c for r, c in solidos if r[-1] == 'pata')
    (x0, y0, z0), (x1, y1, z1) = bbox(pata)
    assert round(z0) == 0 and round(z1) == 660         # 660 mm de alto
    respaldo = next(c for r, c in solidos if r[-1] == 'respaldo')
    assert round(bbox(respaldo)[1][1]) == 0            # atrás (Y = 0); el frente queda en -Y, como Polyboard


def test_con_z_arriba_queda_acostado():
    solidos, _, _ = leer_fusion(SILLON, arriba='z')
    pata = next(c for r, c in solidos if r[-1] == 'pata')
    (_, y0, z0), (_, y1, z1) = bbox(pata)
    assert round(y1 - y0) == 660 and round(z1 - z0) == 30


def test_materiales_elegidos_y_lo_que_no_se_fabrica(tmp_path):
    opciones = {'todo': 'Eucalipto', 'piezas': {'Component16': 'Pino', 'almohadones': '-'}}
    r = convertir(SILLON, [], tmp_path, codigo='x', fusion=opciones)
    d = json.loads(r.archivo.read_text(encoding='utf-8'))
    assert d['muebles'] == ['sillon exterior 2m']
    assert r.resumen['paneles'] == 17 and r.resumen['herrajes'] == 2
    por_nombre = {}
    for p in d['paneles']:
        por_nombre.setdefault(p['nombre'], set()).add(p['mat'])
        assert p['num'] == '' and all(c['mat'] == p['mat'] for c in p['cantos'])   # lados del mismo material
    assert por_nombre == {'Component16': {'Pino'}, 'pata': {'Eucalipto'}, 'viga': {'Eucalipto'},
                          'respaldo': {'Eucalipto'}, 'parrillarespaldo': {'Eucalipto'}}
    assert {h['mueble'] for h in d['herrajes']} == {'sillon exterior 2m'}
    grupos = {g['nombre']: g for g in d['fusion']['grupos']}
    assert grupos['Component16']['cant'] == 7 and grupos['almohadones']['eleccion'] == '-'
    assert not any('sin material' in a for a in r.avisos)
    ids = [p['id'] for p in d['paneles']]
    assert len(ids) == len(set(ids))                    # cada pieza con su id (las 7 de la parrilla también)
    cliente = json.loads((tmp_path / 'clientes' / 'x.json').read_text(encoding='utf-8'))
    assert 'fusion' not in cliente and (tmp_path / 'clientes' / 'x' / 'todo.glb').exists()


def test_sin_material_avisa(tmp_path):
    r = convertir(SILLON, [], tmp_path, codigo='x')
    assert any('sin material' in a.lower() for a in r.avisos)


def test_polyboard_sin_ocp_sigue_pidiendo_la_lista(tmp_path):
    with pytest.raises(ErrorConversion, match='OptiCut'):
        convertir(MUESTRAS / 'Kogan' / 'Kogan.dxf', [], tmp_path)
