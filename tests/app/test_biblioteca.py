"""Importar la biblioteca de materiales de Polyboard a Materiales (proyectos/biblioteca.py), con las bibliotecas de
verdad de Nord Good (muestras/biblioteca)."""
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from proyectos.biblioteca import leer
from proyectos.models import Material
from talleres.separacion import con_taller
from tests.app.ayudas import MUESTRAS

BIBLIOTECA = MUESTRAS / 'biblioteca'


def archivo(nombre):
    return SimpleUploadedFile(nombre, (BIBLIOTECA / nombre).read_bytes())


def jpg():
    b = io.BytesIO()
    Image.new('RGB', (40, 20), (180, 150, 110)).save(b, 'JPEG')
    return SimpleUploadedFile('yute 800x800.jpg', b.getvalue(), 'image/jpeg')


def test_leer_trae_color_o_textura_y_no_los_separadores():
    tableros, cantos = leer(archivo('Panel.mat-boole')), leer(archivo('Edge.mat-boole'))
    assert tableros['f-Tribal'] == {'color': '#92847B'}
    assert tableros['f-Yute'] == {'textura': (r'faplac\yute 800x800.jpg', 1000.0)}
    assert cantos['f-yute'] == {'color': '#804000'}
    assert not [n for n in (*tableros, *cantos) if '---' in n]


@pytest.fixture
def dueno(cliente_de, t):
    return cliente_de(t.dueno_a)


def materiales(t):
    with con_taller(t.A):
        return {(m.tipo, m.nombre): m for m in Material.objects.all()}


def test_importar_y_subir_las_imagenes_que_faltan(dueno, t):
    with con_taller(t.A):
        Material.objects.create(nombre='f-Tribal', color='#111111')            # cargado a mano: no se pisa
    r = dueno.post('/taller-a/materiales/importar/', {'tableros': archivo('Panel.mat-boole'),
                                                       'cantos': archivo('Edge.mat-boole')}, follow=True)
    assert 'Importaste la biblioteca de Polyboard' in r.content.decode()
    m = materiales(t)
    assert m[('tablero', 'f-Tribal')].color == '#111111'
    yute = m[('tablero', 'f-Yute')]
    assert (yute.ruta_polyboard, yute.ancho_mm, yute.color) == (r'faplac\yute 800x800.jpg', 1000, '')
    assert m[('canto', 'f-yute')].color == '#804000'
    pagina = dueno.get('/taller-a/materiales/importar/').content.decode()
    assert r'"ruta": "faplac\\yute 800x800.jpg"' in pagina                  # en el JSON que usa la página

    # paso 2: la imagen de la carpeta Textures
    r =dueno.post('/taller-a/materiales/importar/textura/', {'id': yute.pk, 'archivo': jpg()})
    assert r.json() == {'ok': True}
    assert materiales(t)[('tablero', 'f-Yute')].textura
    assert 'faplac\\yute' not in dueno.get('/taller-a/materiales/importar/').content.decode()
    r = dueno.post('/taller-a/materiales/importar/textura/',
                   {'id': m[('tablero', 'f-Tribal')].pk, 'archivo': SimpleUploadedFile('x.jpg', b'no es imagen')})
    assert r.status_code == 400 and not r.json()['ok']

    # otra vez, reemplazando colores: el que estaba a mano toma el de la biblioteca; nada nuevo
    r = dueno.post('/taller-a/materiales/importar/', {'tableros': archivo('Panel.mat-boole'),
                                                       'reemplazar_colores': 'on'}, follow=True)
    assert ' 0 nuevos' in r.content.decode()
    assert materiales(t)[('tablero', 'f-Tribal')].color == '#92847B'


def test_importar_rechaza_lo_que_no_es_una_biblioteca(dueno, t, cliente_de):
    r = dueno.post('/taller-a/materiales/importar/', {})
    assert r.status_code == 400 and 'Elegí Panel.mat-boole' in r.content.decode()
    r = dueno.post('/taller-a/materiales/importar/', {'tableros': SimpleUploadedFile('Panel.mat-boole', b'basura')})
    assert r.status_code == 400 and 'no trae materiales' in r.content.decode()
    r = dueno.post('/taller-a/materiales/importar/', {'tableros': SimpleUploadedFile('lista.ocp', b'x')})
    assert r.status_code == 400
    assert cliente_de(t.armador_a).get('/taller-a/materiales/importar/').status_code == 403
