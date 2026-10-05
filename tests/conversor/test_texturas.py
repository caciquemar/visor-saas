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
