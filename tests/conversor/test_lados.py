"""Lados de las piezas en los modelos de realidad aumentada (glb_ar), con la misma regla que el visor:
sin canto -> color MDF (el del taller); canto que se llama como el tablero -> igual que el tablero; otro canto -> su color."""
import json
import struct

from conversor.polyboard_a_app import SIN_CANTO, glb_ar, lineal

# Una pieza de 100 x 50 x 18 mm: caras grandes en z = 0 y z = 18; lados en x = 0, x = 100, y = 0, y = 50.
X, Y, Z = 100, 50, 18


def caja():
    v = [[0, 0, 0], [X, 0, 0], [X, Y, 0], [0, Y, 0], [0, 0, Z], [X, 0, Z], [X, Y, Z], [0, Y, Z]]
    caras = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (3, 2, 6, 7), (0, 3, 7, 4), (1, 2, 6, 5)]
    t = []
    for a, b, c, d in caras:
        for i, j, k in ((a, b, c), (a, c, d)):
            t += v[i] + v[j] + v[k]
    return t


def canto(mat, plano):
    """Rectángulo del canto sobre un lado: 'y0' (y = 0), 'y50', 'x0' o 'x100'."""
    eje, valor = plano[0], float(plano[1:])
    if eje == 'y':
        q = [[0, valor, 0], [X, valor, 0], [X, valor, Z], [0, valor, Z]]
    else:
        q = [[valor, 0, 0], [valor, Y, 0], [valor, Y, Z], [valor, 0, Z]]
    return {'mat': mat, 'v': [c for p in q for c in p]}


def materiales_del_glb(glb):
    largo = struct.unpack('<I', glb[12:16])[0]
    doc = json.loads(glb[20:20 + largo])
    return [m['pbrMetallicRoughness']['baseColorFactor'] for m in doc['materials']]


def cerca(a, b):
    return all(abs(x - y) < 1e-6 for x, y in zip(a, b))


def glb(cantos, sin_canto=None):
    datos = {'proyecto': 'Prueba', 'materiales': {'Roble': {'color': '#BA8C5C'}},
             'cantos': {'negro': {'color': '#408080'}}}
    panel = {'mat': 'Roble', 't': caja(), 'cantos': cantos}
    return materiales_del_glb(glb_ar(datos, [panel], [], '.', {}, sin_canto=sin_canto))


def test_sin_cantos_los_lados_son_mdf():
    colores = glb([canto('', 'y0')])
    assert any(cerca(c, lineal(SIN_CANTO)) for c in colores)
    assert len(colores) == 2                                      # tablero + lados sin canto


def test_color_sin_canto_del_taller():
    assert any(cerca(c, lineal('#222222')) for c in glb([], sin_canto='#222222'))


def test_canto_con_el_nombre_del_tablero_va_con_el_tablero():
    colores = glb([canto('roble', 'y0'), canto('Roble', 'y50'), canto('ROBLE', 'x0'), canto('roble', 'x100')])
    assert colores == [lineal('#BA8C5C')]                          # todo en la malla del tablero


def test_otro_canto_con_su_color():
    colores = glb([canto('negro', 'y0'), canto('roble', 'y50')])
    assert any(cerca(c, lineal('#408080')) for c in colores)        # el canto negro
    assert any(cerca(c, lineal(SIN_CANTO)) for c in colores)        # x0 y x100 sin canto
    assert any(cerca(c, lineal('#BA8C5C')) for c in colores)
    assert len(colores) == 3
