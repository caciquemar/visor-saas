"""Ficha 14: probador de colores en el link del cliente.

El proyecto se arma a mano (como en test_visor.py) con un clientes/<código>.json chico pero con geometría de verdad,
así la combinación se genera con el glb_ar del conversor. La prueba con la muestra usa el cliente.json real de
*Rack florencia* (muestras/*/esperado)."""
import gzip
import io
import json
from types import SimpleNamespace

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from proyectos import probador
from proyectos.models import Combinacion, EleccionCliente, GrupoDeColor, Material
from talleres.separacion import OtroTaller, con_taller
from tests.app.ayudas import MUESTRAS
from tests.app.test_visor import config_de, link_de, proyecto_listo
from tests.conversor.test_lados import canto, caja, cerca, materiales_del_glb
from conversor.polyboard_a_app import lineal

BLANCO, NOGAL = '#F0F0EC', '#6F4D35'


def jpg():
    b = io.BytesIO()
    Image.new('RGB', (8, 8), (111, 77, 53)).save(b, 'JPEG')
    return b.getvalue()


def cliente_chico(cc):
    """Dos muebles: Bajo (Roble, con un canto 'roble' y otro 'negro') y Alto (Melamina blanca)."""
    return {'proyecto': 'Cocina', 'muebles': ['Alto', 'Bajo'],
            'paneles': [{'mueble': 'Bajo', 'mat': 'Roble', 't': caja(),
                         'cantos': [canto('roble', 'y0'), canto('negro', 'y50')]},
                        {'mueble': 'Alto', 'mat': 'Melamina blanca', 't': caja(), 'cantos': []}],
            'herrajes': [], 'muros': [],
            'materiales': {'Roble': {'textura': 'texturas/1-abc.jpg'}, 'Melamina blanca': {'color': '#FFFFFF'}},
            'cantos': {'negro': {'color': '#408080'}, 'roble': {'color': '#BA8C5C'}},
            'ar': {'': f'{cc}/todo.glb'}}


def preparar(taller, nombre='Cocina'):
    """Proyecto listo con cliente.json chico, dos tableros en la biblioteca (Blanco con color, Nogal con textura),
    un canto que se llama Nogal (no se ofrece nunca) y un grupo "Frentes" = Roble."""
    p = proyecto_listo(taller, nombre=nombre)
    with con_taller(taller):
        v = p.version_actual
        ruta = probador.ruta_cliente(v)
        default_storage.delete(ruta)
        default_storage.save(ruta, ContentFile(json.dumps(cliente_chico(p.codigo_cliente)).encode()))
        default_storage.delete(f'{v.carpeta()}resultado/texturas/1-abc.jpg')
        default_storage.save(f'{v.carpeta()}resultado/texturas/1-abc.jpg', ContentFile(jpg()))
        blanco = Material.objects.create(nombre='Blanco', color=BLANCO)
        nogal = Material.objects.create(nombre='Nogal', ancho_mm=2800,
                                        textura=SimpleUploadedFile('nogal.jpg', jpg(), 'image/jpeg'))
        canto_nogal = Material.objects.create(nombre='Nogal', tipo=Material.Tipo.CANTO, color='#000000')
        grupo = GrupoDeColor.objects.create(proyecto=p, nombre='Frentes', tableros=['Roble'],
                                            opciones=[blanco.pk, nogal.pk])
    return SimpleNamespace(p=p, v=v, blanco=blanco, nogal=nogal, canto_nogal=canto_nogal, grupo=grupo)


@pytest.fixture
def a(t):
    return preparar(t.A)


@pytest.fixture
def link(t, a):
    return link_de(t.A, a.p)


def pedir(client, link, que, cuerpo):
    return client.post(f'/c/{link.codigo}/probador/{que}', json.dumps(cuerpo), content_type='application/json')


# ---------------------------------------------------------------- sustitución

def material(nombre, color=None, pk=1, textura=None):
    return SimpleNamespace(nombre=nombre, color=color, pk=pk, textura=textura, ancho_mm=None)


def test_sustituir_cambia_tablero_y_cantos_con_su_nombre():
    d = probador.sustituir(cliente_chico('cc'), {'Roble': material('Blanco', BLANCO)})
    bajo, alto = d['paneles']
    assert bajo['mat'] == 'Blanco' and alto['mat'] == 'Melamina blanca'
    assert [c['mat'] for c in bajo['cantos']] == ['Blanco', 'negro']      # 'roble' acompaña, 'negro' queda
    assert d['materiales']['Blanco'] == {'color': BLANCO}
    assert d['cantos']['Blanco'] == {'color': BLANCO}


def test_sustituir_varios_tableros_en_un_grupo_y_no_toca_el_original():
    original = cliente_chico('cc')
    d = probador.sustituir(original, {'Roble': material('Blanco'), 'Melamina blanca': material('Blanco')})
    assert {p['mat'] for p in d['paneles']} == {'Blanco'}
    assert original['paneles'][0]['mat'] == 'Roble'


def test_el_glb_de_la_combinacion_lleva_el_tablero_nuevo_en_caras_y_canto(tmp_path):
    d = probador.sustituir(cliente_chico('cc'), {'Roble': material('Blanco', BLANCO)})
    from conversor.polyboard_a_app import glb_ar
    colores = materiales_del_glb(glb_ar(d, d['paneles'][:1], [], tmp_path, {}))
    assert any(cerca(c, lineal(BLANCO)) for c in colores)
    assert any(cerca(c, lineal('#408080')) for c in colores)              # el canto negro sigue
    assert not any(cerca(c, lineal('#BA8C5C')) for c in colores)          # ningún lado queda roble


# ---------------------------------------------------------------- pantalla del taller

def test_el_taller_arma_un_grupo_y_ve_las_elecciones(cliente_de, t, a):
    c = cliente_de(t.oficina_a)
    r = c.post(f'/taller-a/proyectos/{a.p.pk}/colores/nuevo/',
               {'nombre': 'Cuerpos', 'tablero': ['Melamina blanca', 'Inventado'],
                'opcion': [a.blanco.pk, a.canto_nogal.pk]})
    assert r.status_code == 302
    with con_taller(t.A):
        g = GrupoDeColor.objects.get(nombre='Cuerpos')
    assert g.tableros == ['Melamina blanca'] and g.opciones == [a.blanco.pk]   # sin el inventado ni el canto
    html = c.get(f'/taller-a/proyectos/{a.p.pk}/?ver=cliente').content.decode()
    assert 'Probador de colores' in html and 'Cuerpos' in html
    # borrar
    c.post(f'/taller-a/proyectos/{a.p.pk}/colores/{g.pk}/', {'borrar': '1'})
    with con_taller(t.A):
        assert not GrupoDeColor.objects.filter(pk=g.pk).exists()


def test_grupo_incompleto_no_se_guarda(cliente_de, t, a):
    cliente_de(t.dueno_a).post(f'/taller-a/proyectos/{a.p.pk}/colores/nuevo/', {'nombre': 'X', 'tablero': ['Roble']})
    with con_taller(t.A):
        assert not GrupoDeColor.objects.filter(nombre='X').exists()


def test_agregar_un_tablero_a_la_biblioteca(cliente_de, t, a):
    c = cliente_de(t.oficina_a)
    r = c.post('/taller-a/materiales/nuevo-tablero/', {'nombre': ' Cedro  claro ', 'color': '#c9966a'})
    assert r.status_code == 302
    with con_taller(t.A):
        m = Material.objects.get(clave='cedro claro')
    assert m.tipo == Material.Tipo.TABLERO and m.nombre == 'Cedro claro' and m.color == '#C9966A'
    r = c.post('/taller-a/materiales/nuevo-tablero/', {'nombre': 'Cedro Claro', 'color': '#000000'})
    assert r.status_code == 400 and 'Ya tenés el tablero' in r.content.decode()
    r = c.post('/taller-a/materiales/nuevo-tablero/', {'nombre': 'Haya'})
    assert r.status_code == 400 and 'Subí la imagen o poné un color' in r.content.decode()
    r = c.post('/taller-a/materiales/nuevo-tablero/',
               {'nombre': 'Haya', 'textura': SimpleUploadedFile('h.jpg', jpg(), 'image/jpeg')})
    assert r.status_code == 302
    assert cliente_de(t.armador_a).post('/taller-a/materiales/nuevo-tablero/',
                                        {'nombre': 'Pino', 'color': '#DAB97F'}).status_code == 403


def test_armador_no_arma_grupos(cliente_de, t, a):
    r = cliente_de(t.armador_a).post(f'/taller-a/proyectos/{a.p.pk}/colores/nuevo/',
                                     {'nombre': 'X', 'tablero': ['Roble'], 'opcion': [a.blanco.pk]})
    assert r.status_code == 403


# ---------------------------------------------------------------- link del cliente

def test_el_link_trae_el_probador_y_el_visor_del_taller_no(client, cliente_de, t, a, link):
    config = config_de(client.get(f'/c/{link.codigo}/'))
    assert config['csrf']
    [g] = config['probador']
    assert g['nombre'] == 'Frentes' and g['tableros'] == ['Roble']
    assert [o['nombre'] for o in g['opciones']] == ['Blanco', 'Nogal']
    assert g['opciones'][1]['textura'] == f'opciones/{a.nogal.pk}.jpg' and g['opciones'][1]['ancho'] == 2800
    assert 'probador' not in config_de(cliente_de(t.dueno_a).get('/taller-a/visor/'))


def test_sin_grupos_no_hay_probador(client, t):
    p = proyecto_listo(t.A)
    config = config_de(client.get(f'/c/{link_de(t.A, p).codigo}/'))
    assert 'probador' not in config and 'csrf' not in config


def test_textura_de_una_opcion_solo_si_se_ofrece(client, t, a, link):
    assert client.get(f'/c/{link.codigo}/data/opciones/{a.nogal.pk}.jpg').status_code == 200
    with con_taller(t.A):
        otro = Material.objects.create(nombre='Cedro', textura=SimpleUploadedFile('c.jpg', jpg(), 'image/jpeg'))
    assert client.get(f'/c/{link.codigo}/data/opciones/{otro.pk}.jpg').status_code == 404
    assert client.get(f'/c/{link.codigo}/data/opciones/{a.blanco.pk}.jpg').status_code == 404     # sin imagen


def test_ar_de_una_combinacion(client, t, a, link, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        r = pedir(client, link, 'ar', {'elecciones': {str(a.grupo.pk): a.nogal.pk}})
    assert r.json() == {'estado': 'preparando'}
    j = pedir(client, link, 'ar', {'elecciones': {str(a.grupo.pk): a.nogal.pk}}).json()
    assert j['estado'] == 'lista' and set(j['ar']) == {'', 'Alto', 'Bajo'}
    glb = client.get(f'/c/{link.codigo}/data/{j["ar"][""]}')
    assert glb.status_code == 200
    contenido = b''.join(glb.streaming_content) if glb.streaming else glb.content
    largo = int.from_bytes(contenido[12:16], 'little')
    assert json.loads(contenido[20:20 + largo])['images']           # la textura de Nogal va adentro
    # otra clave en la misma carpeta, o un GLB que no es de la combinación: 404
    assert client.get(f'/c/{link.codigo}/data/combinaciones/abc/todo.glb').status_code == 404


def test_como_esta_no_genera_nada(client, t, a, link):
    assert pedir(client, link, 'ar', {'elecciones': {}}).json() == {'estado': 'lista', 'ar': {}}
    assert pedir(client, link, 'ar', {'elecciones': {str(a.grupo.pk): 99999}}).json()['ar'] == {}
    with con_taller(t.A):
        assert not Combinacion.objects.exists()


def test_limite_de_combinaciones(client, t, a, link, monkeypatch):
    monkeypatch.setattr(probador, 'LIMITE_COMBINACIONES', 1)
    assert pedir(client, link, 'ar', {'elecciones': {str(a.grupo.pk): a.blanco.pk}}).json()['estado'] != 'celular'
    assert pedir(client, link, 'ar', {'elecciones': {str(a.grupo.pk): a.nogal.pk}}).json() == {'estado': 'celular'}


def test_tope_de_combinaciones_nuevas_por_ip(client, t, a, link, monkeypatch):
    from proyectos import visor
    monkeypatch.setattr(visor, 'NUEVAS_POR_IP', 1)
    pedir(client, link, 'ar', {'elecciones': {str(a.grupo.pk): a.blanco.pk}})
    assert pedir(client, link, 'ar', {'elecciones': {str(a.grupo.pk): a.nogal.pk}}).json() == {'estado': 'celular'}
    # la que ya existe se sigue pudiendo pedir
    assert pedir(client, link, 'ar', {'elecciones': {str(a.grupo.pk): a.blanco.pk}}).json()['estado'] != 'celular'


def test_me_gusta_esta(client, cliente_de, t, a, link):
    r = pedir(client, link, 'elegir', {'elecciones': {str(a.grupo.pk): a.nogal.pk}, 'nombre': ' Carla ',
                                       'comentario': 'Con manijas negras'})
    assert r.json() == {'ok': True}
    with con_taller(t.A):
        e = EleccionCliente.objects.get()
    assert e.nombre == 'Carla' and e.link_id == link.pk and e.version_id == a.v.pk
    assert e.elecciones == [{'grupo': 'Frentes', 'tableros': ['Roble'], 'elegido': 'Nogal'}]
    html = cliente_de(t.armador_a).get(f'/taller-a/proyectos/{a.p.pk}/?ver=cliente').content.decode()
    assert 'Carla' in html and 'Nogal' in html and 'Con manijas negras' in html
    assert pedir(client, link, 'elegir', {'elecciones': {}, 'nombre': ''}).status_code == 400


def test_me_gusta_esta_tiene_tope(client, t, a, link, monkeypatch):
    from proyectos import visor
    monkeypatch.setattr(visor, 'ELECCIONES_POR_IP', 1)
    assert pedir(client, link, 'elegir', {'nombre': 'Carla'}).status_code == 200
    assert pedir(client, link, 'elegir', {'nombre': 'Carla'}).status_code == 429


def test_link_anulado_o_inexistente(client, t, a, link):
    from django.utils import timezone
    with con_taller(t.A):
        link.anulado = timezone.now()
        link.save()
    assert pedir(client, link, 'ar', {'elecciones': {}}).status_code == 404
    assert pedir(client, link, 'elegir', {'nombre': 'x'}).status_code == 404
    assert client.get(f'/c/{link.codigo}/data/opciones/{a.nogal.pk}.jpg').status_code == 404


def test_pedido_que_no_es_json(client, t, a, link):
    r = client.post(f'/c/{link.codigo}/probador/ar', 'no', content_type='application/json')
    assert r.status_code == 400


# ---------------------------------------------------------------- separación

def test_nada_del_probador_cruza_entre_talleres(client, cliente_de, t, a, link):
    b = preparar(t.B, nombre='Placard de B')
    link_b = link_de(t.B, b.p)
    # la opción de B no se ve desde el link de A, ni sus grupos, ni las opciones de A desde el link de B
    assert client.get(f'/c/{link.codigo}/data/opciones/{b.nogal.pk}.jpg').status_code == 404
    assert client.get(f'/c/{link_b.codigo}/data/opciones/{a.nogal.pk}.jpg').status_code == 404
    assert pedir(client, link, 'ar', {'elecciones': {str(b.grupo.pk): b.nogal.pk}}).json()['ar'] == {}
    # desde A no se edita un grupo de B
    r = cliente_de(t.dueno_a).post(f'/taller-a/proyectos/{a.p.pk}/colores/{b.grupo.pk}/', {'borrar': '1'})
    assert r.status_code == 404
    with con_taller(t.A):
        assert not GrupoDeColor.objects.filter(pk=b.grupo.pk).exists()
        with pytest.raises(OtroTaller):
            GrupoDeColor.objects.create(proyecto=b.p, nombre='X')
        with pytest.raises(OtroTaller):
            EleccionCliente.objects.create(proyecto=b.p, nombre='X')
        with pytest.raises(OtroTaller):
            Combinacion.objects.create(version=b.v, clave='x')


# ---------------------------------------------------------------- con una muestra real

@pytest.mark.muestras
def test_combinacion_con_rack_florencia(tmp_path):
    cliente = json.loads(gzip.decompress((MUESTRAS / 'Rack florencia' / 'esperado' / 'cliente.json.gz').read_bytes()))
    tableros = probador.tableros_de(cliente)
    assert len(tableros) >= 2
    cambios = {tableros[0]: material('Prueba claro', BLANCO), tableros[1]: material('Prueba oscuro', NOGAL, pk=2)}
    d = probador.sustituir(cliente, cambios)
    assert not {p['mat'] for p in d['paneles']} & set(tableros[:2])
    from conversor.polyboard_a_app import glb_ar
    colores = materiales_del_glb(glb_ar(d, d['paneles'], d['herrajes'], tmp_path, {}))
    assert any(cerca(c, lineal(BLANCO)) for c in colores) and any(cerca(c, lineal(NOGAL)) for c in colores)


def test_opcion_con_veta_vertical_va_girada_y_con_su_alto():
    from proyectos.models import Material
    from proyectos.probador import info_de
    m = Material(nombre='Nogal', textura='talleres/1/material/nogal.jpg', proporcion=2.0, veta_detectada='v')
    assert info_de(m) == {'textura': 'opciones/None.jpg', 'ancho': 1000, 'alto': 2000, 'girar': 1}
    m.veta, m.ancho_mm = 'h', 600                       # elegida a mano: manda sobre la detectada
    assert info_de(m) == {'textura': 'opciones/None.jpg', 'ancho': 600, 'alto': 1200}
