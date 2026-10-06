"""Copia reducida de las texturas, con imágenes generadas en el momento (sin la carpeta de Polyboard)."""
from PIL import Image

from conversor.polyboard_a_app import Texturas


def rayada(ruta, ancho, alto, vertical):
    """Imagen con vetas: rayas verticales (veta vertical) u horizontales."""
    im = Image.new('RGB', (ancho, alto))
    for x in range(ancho):
        for y in range(alto):
            v = (x if vertical else y) % 8 < 4
            im.putpixel((x, y), (200, 150, 100) if v else (120, 80, 40))
    im.save(ruta)
    return ruta


def texturas(tmp_path, carpeta):
    return Texturas([carpeta], None, tmp_path / 'salida', [])


def test_veta_horizontal_queda_igual(tmp_path):
    img = rayada(tmp_path / 'roble.png', 300, 100, vertical=False)
    info = texturas(tmp_path, tmp_path).procesar(img, 600, True)
    copia = Image.open(tmp_path / 'salida' / info['textura'])
    assert copia.size == (256, 128)                  # potencias de 2
    assert (info['ancho'], info['alto']) == (600, 200)  # mm que cubre la imagen
    assert info['color'].startswith('#') and len(info['color']) == 7


def test_veta_vertical_se_gira(tmp_path):
    img = rayada(tmp_path / 'nogal.png', 300, 100, vertical=True)
    info = texturas(tmp_path, tmp_path).procesar(img, 600, False)
    copia = Image.open(tmp_path / 'salida' / info['textura'])
    assert copia.size == (128, 256)
    assert (info['ancho'], info['alto']) == (200, 600)
    assert 'color' not in info


def test_sin_escala_usa_un_metro(tmp_path):
    img = rayada(tmp_path / 'lino.jpg', 100, 50, vertical=False)
    info = texturas(tmp_path, tmp_path).procesar(img, None, True)
    assert (info['ancho'], info['alto']) == (1000, 500)


def test_buscar_por_ruta_y_por_nombre(tmp_path):
    (tmp_path / 'Egger').mkdir()
    img = rayada(tmp_path / 'Egger' / 'H1145.jpg', 16, 16, vertical=False)
    t = texturas(tmp_path, tmp_path)
    assert t.buscar(r'Egger\H1145.jpg') == img           # como la guarda Polyboard
    assert t.buscar(r'Otra carpeta\h1145.JPG') == img     # otra carpeta y otra mayúscula
    assert t.buscar(r'Egger\no-existe.jpg') is None


def test_carpeta_inexistente_es_aviso(tmp_path):
    t = Texturas([tmp_path / 'no-existe'], tmp_path / 'tampoco', tmp_path, [])
    assert any('no existe la carpeta de texturas' in a for a in t.avisos)
    assert any('biblioteca de materiales' in a for a in t.avisos)


# ---------------------------------------------------------------- tableros y cantos por separado

import json  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from conversor import convertir  # noqa: E402
from conversor.polyboard_a_app import materiales_del_ocp, resolver_materiales  # noqa: E402

MUESTRAS = Path(__file__).resolve().parents[2] / 'muestras'


def test_ocp_separa_tableros_y_cantos_con_el_mismo_nombre():
    kogan = materiales_del_ocp(MUESTRAS / 'Kogan' / 'Kogan.ocp')
    # mismo nombre exacto, dos materiales distintos
    assert kogan['tableros']['f-Grey Extreme Matt']['color'] == '#5B5D5A'
    assert kogan['cantos']['f-Grey Extreme Matt']['color'] == '#408080'
    rack = materiales_del_ocp(MUESTRAS / 'Rack florencia' / 'Rack florencia.ocp')
    assert 'Blanco' in rack['tableros'] and 'Blanco' not in rack['cantos']
    assert 'blanco' in rack['cantos'] and 'blanco' not in rack['tableros']
    assert rack['tableros']['c-guatambu']['textura'] == (r'enchapados\enchapado guatambu.jpg', 500.0)
    assert 'textura' not in rack['cantos']['c-guatambu']


@pytest.mark.parametrize('ocp', sorted(MUESTRAS.glob('*/*.ocp')), ids=lambda p: p.parent.name)
def test_todas_las_muestras_se_separan(ocp):
    m = materiales_del_ocp(ocp)
    assert m['tableros'] and m['cantos']
    assert m['tableros'] != m['cantos']          # si no se pudiera separar, quedarían iguales


def rayadas(carpeta, *nombres):
    for n in nombres:
        rayada(carpeta / n, 32, 16, vertical=False)


def con_materiales_json(tmp_path, contenido):
    salida = tmp_path / 'salida'
    salida.mkdir()
    (salida / 'materiales.json').write_text(json.dumps(contenido), encoding='utf-8')
    return Texturas([tmp_path], None, salida, [])


def test_materiales_json_separado_por_tipo(tmp_path):
    rayadas(tmp_path, 'tablero.png', 'canto.png')
    t = con_materiales_json(tmp_path, {'tableros': {'Roble': {'textura': 'tablero.png', 'ancho': 600}},
                                       'cantos': {'Roble': {'textura': 'canto.png'}, 'Negro': {'color': '#111111'}}})
    tablero, canto = t.material('Roble', False), t.material('Roble', True)
    assert tablero['textura'] != canto['textura']
    assert tablero['ancho'] == 600 and canto['ancho'] == 1000
    assert t.material('Negro', True)['color'] == '#111111'
    assert 'color' not in t.material('Negro', False)       # el canto no le da color al tablero


def test_materiales_json_plano_vale_para_los_dos(tmp_path):
    rayadas(tmp_path, 'roble.png')
    t = con_materiales_json(tmp_path, {'Roble': 'roble.png', 'Negro': '#111111'})
    assert t.material('Roble', False)['textura'] == t.material('Roble', True)['textura']
    assert t.material('Negro', False)['color'] == t.material('Negro', True)['color'] == '#111111'


def test_resolver_devuelve_tableros_y_cantos(tmp_path):
    rayadas(tmp_path, 'tablero.png', 'canto.png')
    t = con_materiales_json(tmp_path, {'tableros': {'Roble': {'textura': 'tablero.png'}},
                                       'cantos': {'Roble': {'textura': 'canto.png'}}})
    tableros, cantos = resolver_materiales([{'mat': 'Roble', 'cantos': [{'mat': 'Roble'}]}], t)
    assert tableros['Roble']['textura'] != cantos['Roble']['textura']


@pytest.mark.muestras
def test_proyecto_convertido_con_tableros_y_cantos(tmp_path):
    texturas = tmp_path / 'Textures'
    (texturas / 'enchapados').mkdir(parents=True)
    rayada(texturas / 'enchapados' / 'enchapado guatambu.jpg', 64, 32, vertical=False)
    (tmp_path / 'Materials').mkdir()
    carpeta = MUESTRAS / 'Rack florencia'
    r = convertir(carpeta / 'Rack florencia.dxf', [carpeta / 'Rack florencia.ocp'], tmp_path / 'salida', [texturas],
                  biblioteca=tmp_path / 'Materials', codigo='muestra')
    datos = json.loads(r.archivo.read_text(encoding='utf-8'))
    assert datos['materiales']['c-guatambu']['textura'].startswith('texturas/')      # tablero
    assert 'textura' not in datos['cantos']['c-guatambu']                             # canto: solo color
    assert datos['cantos']['c-guatambu']['color'] == '#804000'
    assert 'blanco' in datos['materiales'] and 'blanco' in datos['cantos']   # canto sin tablero homónimo
    assert any(a.startswith('canto blanco: no se encontró la imagen') for a in r.avisos)
    cliente = json.loads((tmp_path / 'salida' / 'clientes' / 'muestra.json').read_text(encoding='utf-8'))
    assert cliente['cantos'] == datos['cantos']
