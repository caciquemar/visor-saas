"""Ficha 05: trabajos a realizar y fotos (trabajos/api.py), con las mismas reglas que referencia/api_actual.py, y
las pruebas de cruce entre talleres para trabajos y fotos."""
import io
import json
import re

import pytest
from django.core.files.storage import default_storage
from django.test import Client
from PIL import Image

from talleres.archivos import abrir_de_taller
from talleres.separacion import OtroTaller, con_taller
from trabajos import api
from trabajos.models import CambioDeEstado, Foto, Trabajo
from tests.app.test_visor import config_de, link_de, proyecto_listo

API = '/taller-a/visor/api/'
API_B = '/taller-b/visor/api/'


def imagen(formato='JPEG', lado=20):
    b = io.BytesIO()
    Image.new('RGB', (lado, lado), (200, 100, 50)).save(b, formato)
    return b.getvalue()


def nuevo(c, p, /, base=API, **campos):
    return c.post(base + 'trabajos', json.dumps({'proyecto': p.pk, 'texto': 'Cambiar la bisagra', **campos}),
                  content_type='application/json')


def cambiar(c, id, base=API, **campos):
    return c.patch(f'{base}trabajos/{id}', json.dumps(campos), content_type='application/json')


def subir_foto(c, id, datos=None, tipo='image/jpeg', base=API):
    return c.post(f'{base}trabajos/{id}/fotos', datos if datos is not None else imagen(), content_type=tipo)


def lista(c, proyecto, base=API):
    r = c.get(f'{base}trabajos', {'proyecto': proyecto.pk})
    assert r.status_code == 200, r.content
    return r.json()


@pytest.fixture
def pa(t):
    return proyecto_listo(t.A)


@pytest.fixture
def pb(t):
    return proyecto_listo(t.B, nombre='Placard de B')


@pytest.fixture
def ana(cliente_de, t):
    return cliente_de(t.dueno_a)


def como(usuario):
    c = Client()
    c.force_login(usuario)
    return c


# ---------------------------------------------------------------- como api.py

def test_pide_login(client, t, pa):
    r = client.get(API + 'trabajos', {'proyecto': pa.pk})
    assert r.status_code == 302 and r['Location'].startswith('/entrar/')
    assert nuevo(client, pa).status_code == 302
    assert not Trabajo.sin_filtro.exists()


def test_anotar_y_listar(ana, t, pa):
    r = nuevo(ana, pa, piezas=['b12', '0053'], muebles=['Bajo'], asignado=t.armador_a.pk, limite='2026-11-02',
              autor='Otro nombre', quien='Otro')
    assert r.status_code == 201, r.content
    d = r.json()
    assert d['autor'] == 'Ana'                       # de la sesión, no del pedido
    assert d['asignado'] == 'Arturo' and d['asignado_id'] == t.armador_a.pk
    assert d['estado'] == 'pendiente' and d['limite'] == '2026-11-02' and d['proyecto'] == pa.pk
    assert d['piezas'] == ['b12', '0053'] and d['muebles'] == ['Bajo'] and d['fotos'] == []
    assert re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}', d['creado'])
    assert d['iniciado_por'] is d['iniciado_en'] is d['hecho_en'] is d['instalado_en'] is None
    assert d['puede_editar'] is True
    assert lista(ana, pa) == [d]


def test_orden_por_estado_y_mas_nuevo_primero(ana, pa):
    ids = [nuevo(ana, pa, texto=f't{i}').json()['id'] for i in range(5)]
    for i, e in zip(ids, ('instalado', 'hecho', 'en proceso', 'pendiente', 'pendiente')):
        if e != 'pendiente':
            assert cambiar(ana, i, estado=e).status_code == 200
    assert [x['id'] for x in lista(ana, pa)] == [ids[4], ids[3], ids[2], ids[1], ids[0]]


def test_cada_proyecto_tiene_sus_trabajos(ana, t, pa):
    otro = proyecto_listo(t.A, nombre='Cocina')         # mismo nombre: por eso va el id
    nuevo(ana, pa)
    assert lista(ana, otro) == []


def test_pasos_de_estado_quien_y_cuando(ana, cliente_de, t, pa):
    i = nuevo(ana, pa).json()['id']
    d = cambiar(ana, i, estado='hecho', quien='Otro').json()      # se saltea "en proceso": se completa igual
    assert d['estado'] == 'hecho'
    assert d['iniciado_por'] == d['hecho_por'] == 'Ana' and d['iniciado_en'] == d['hecho_en']
    arturo = como(t.armador_a)
    d = cambiar(arturo, i, estado='instalado').json()
    assert d['instalado_por'] == 'Arturo' and d['hecho_por'] == 'Ana'
    d = cambiar(arturo, i, estado='en proceso').json()            # volver atrás borra los pasos posteriores
    assert d['iniciado_por'] == 'Arturo'
    assert d['hecho_por'] is d['hecho_en'] is d['instalado_por'] is d['instalado_en'] is None
    d = cambiar(arturo, i, estado='en proceso').json()            # mismo estado: no cambia nada
    with con_taller(t.A):
        cambios = list(CambioDeEstado.objects.filter(trabajo_id=i).values_list('de', 'a', 'usuario__nombre'))
    assert cambios == [('pendiente', 'hecho', 'Ana'), ('hecho', 'instalado', 'Arturo'),
                       ('instalado', 'en proceso', 'Arturo')]


@pytest.mark.parametrize('campos,error', [
    ({'texto': ''}, 'falta el texto'),
    ({'texto': '  '}, 'falta el texto'),
    ({'texto': 'x' * 4001}, 'texto no válido'),
    ({'limite': '2/11/2026'}, 'limite debe ser AAAA-MM-DD'),
    ({'limite': '2026-13-40'}, 'limite debe ser AAAA-MM-DD'),
    ({'estado': 'terminado'}, 'estado no válido'),
    ({'piezas': 'b12'}, 'piezas no válido'),
    ({'piezas': ['x'] * 501}, 'piezas no válido'),
    ({'muebles': [1]}, 'muebles no válido'),
    ({'muebles': ['x' * 201]}, 'muebles no válido'),
    ({'asignado': 'Arturo'}, 'asignado no válido'),
    ({'proyecto': 'Cocina'}, 'falta el proyecto'),
])
def test_validaciones(ana, pa, campos, error):
    r = nuevo(ana, pa, **campos)
    assert r.status_code == 400 and r.json()['error'].startswith(error)
    assert not Trabajo.sin_filtro.exists()


def test_cuerpo_que_no_es_json(ana, pa):
    for cuerpo in ('no es json', '[1, 2]', '"texto"'):
        r = ana.post(API + 'trabajos', cuerpo, content_type='application/json')
        assert r.status_code == 400 and r.json() == {'error': 'se esperaba un objeto JSON'}


def test_no_existe_y_metodos(ana, pa):
    assert cambiar(ana, 999, texto='x').status_code == 404
    assert cambiar(ana, 999, texto='x').json() == {'error': 'no existe'}
    assert ana.delete(API + 'trabajos/999').status_code == 404
    assert ana.get(API + 'trabajos', {'proyecto': 999}).status_code == 404
    assert ana.get(API + 'trabajos').status_code == 400
    assert ana.put(API + 'trabajos').status_code == 405
    assert ana.get(API + 'fotos/999').status_code == 404


# ---------------------------------------------------------------- para quién: solo gente del taller

def test_asignado_solo_gente_activa_del_taller(ana, t, pa):
    assert nuevo(ana, pa, asignado=t.dueno_b.pk).json() == {'error': 'asignado no es del taller'}
    assert nuevo(ana, pa, asignado=t.armador_b.pk).status_code == 400
    i = nuevo(ana, pa, asignado=t.armador_a.pk).json()['id']
    with con_taller(t.A):
        t.m_armador_a.activa = False
        t.m_armador_a.save()
    assert nuevo(ana, pa, asignado=t.armador_a.pk).status_code == 400
    # el que ya tenía el trabajo lo conserva al guardar sin cambiarlo (el formulario manda todo)
    d = cambiar(ana, i, texto='otro texto', asignado=t.armador_a.pk).json()
    assert d['asignado'] == 'Arturo' and d['texto'] == 'otro texto'
    assert cambiar(ana, i, asignado=None).json()['asignado'] is None
    assert cambiar(ana, i, asignado=t.oficina_a.pk).json()['asignado'] == 'Olga'


# ---------------------------------------------------------------- quién puede qué

def test_cualquiera_cambia_el_estado_pero_editar_y_borrar_es_del_autor_o_gestion(ana, t, pa):
    i = nuevo(ana, pa).json()['id']
    arturo = como(t.armador_a)
    assert lista(arturo, pa)[0]['puede_editar'] is False
    assert cambiar(arturo, i, estado='en proceso').status_code == 200
    r = cambiar(arturo, i, texto='otra cosa')
    assert r.status_code == 403 and 'Solo quien lo anotó' in r.json()['error']
    assert cambiar(arturo, i, limite='2027-01-01').status_code == 403
    assert arturo.delete(f'{API}trabajos/{i}').status_code == 403
    # el formulario manda todo: con lo mismo de antes y otro estado, es solo un cambio de estado
    d = lista(arturo, pa)[0]
    assert cambiar(arturo, i, texto=d['texto'], asignado=None, limite=None, piezas=[], muebles=[],
                   estado='hecho').status_code == 200
    # lo suyo sí
    propio = nuevo(arturo, pa, texto='mío').json()
    assert propio['puede_editar'] is True
    assert cambiar(arturo, propio['id'], texto='mío, corregido').status_code == 200
    assert arturo.delete(f"{API}trabajos/{propio['id']}").status_code == 204
    # la oficina, todo
    olga = como(t.oficina_a)
    assert cambiar(olga, i, texto='corregido por Olga').json()['texto'] == 'corregido por Olga'
    assert olga.delete(f'{API}trabajos/{i}').status_code == 204
    assert lista(ana, pa) == []


# ---------------------------------------------------------------- fotos

def test_subir_ver_y_quitar_fotos(ana, t, pa, django_capture_on_commit_callbacks):
    i = nuevo(ana, pa).json()['id']
    for formato, tipo in (('JPEG', 'image/jpeg'), ('PNG', 'image/png'), ('WEBP', 'image/webp')):
        r = subir_foto(ana, i, imagen(formato), tipo)
        assert r.status_code == 200, r.content
    fotos = r.json()['fotos']
    assert len(fotos) == 3
    with con_taller(t.A):
        archivos = [f.archivo.name for f in Foto.objects.order_by('pk')]
    assert all(a.startswith(f'talleres/{t.A.pk}/foto/') for a in archivos)
    assert [a.rsplit('.', 1)[1] for a in archivos] == ['jpg', 'png', 'webp']
    r = ana.get(f'{API}fotos/{fotos[0]}')
    assert r.status_code == 200 and b''.join(r.streaming_content) == imagen()
    assert 'immutable' in r['Cache-Control']
    with django_capture_on_commit_callbacks(execute=True):
        d = ana.delete(f'{API}trabajos/{i}/fotos/{fotos[0]}').json()
    assert d['fotos'] == fotos[1:]
    assert not default_storage.exists(archivos[0]) and default_storage.exists(archivos[1])
    with django_capture_on_commit_callbacks(execute=True):
        assert ana.delete(f'{API}trabajos/{i}').status_code == 204
    assert not any(default_storage.exists(a) for a in archivos)
    assert not Foto.sin_filtro.exists()


def test_fotos_rechazadas(ana, t, pa, monkeypatch):
    i = nuevo(ana, pa).json()['id']
    casos = [
        (subir_foto(ana, i, imagen(), 'image/gif'), 415),
        (subir_foto(ana, i, imagen(), 'text/plain'), 415),
        (subir_foto(ana, i, b'esto no es una imagen'), 415),
        (subir_foto(ana, i, imagen('PNG'), 'image/jpeg'), 415),     # dice JPEG y es PNG
        (subir_foto(ana, i, imagen()[:60]), 415),                   # cortada
        (ana.generic('POST', f'{API}trabajos/{i}/fotos', b'', CONTENT_TYPE='image/jpeg'), 413),   # vacía
    ]
    for r, codigo in casos:
        assert r.status_code == codigo, r.content
    assert subir_foto(ana, 999).status_code == 404
    monkeypatch.setattr(api, 'MAX_FOTO', 100)
    r = subir_foto(ana, i, imagen())
    assert r.status_code == 413 and r.json() == {'error': 'imagen vacía o demasiado grande'}
    assert not Foto.sin_filtro.exists()


def test_fotos_doce_mb_como_hoy():
    assert api.MAX_FOTO == 12 * 1024 * 1024
    assert set(api.TIPOS_FOTO) == {'image/jpeg', 'image/png', 'image/webp'}


def test_quitar_foto_ajena(ana, t, pa):
    i = nuevo(ana, pa).json()['id']
    arturo = como(t.armador_a)
    de_ana = subir_foto(ana, i).json()['fotos'][0]
    de_arturo = subir_foto(arturo, i).json()['fotos'][1]       # cualquiera suma fotos
    assert arturo.delete(f'{API}trabajos/{i}/fotos/{de_ana}').status_code == 403
    assert arturo.delete(f'{API}trabajos/{i}/fotos/{de_arturo}').status_code == 200


def test_foto_por_el_trabajo_equivocado(ana, pa):
    i = nuevo(ana, pa).json()['id']
    j = nuevo(ana, pa).json()['id']
    f = subir_foto(ana, i).json()['fotos'][0]
    assert ana.delete(f'{API}trabajos/{j}/fotos/{f}').status_code == 404
    assert len(lista(ana, pa)[1]['fotos']) == 1


# ---------------------------------------------------------------- CSRF y límites por plan

def test_sin_token_csrf_no_se_cambia_nada(t, pa):
    c = Client(enforce_csrf_checks=True)
    c.force_login(t.dueno_a)
    assert nuevo(c, pa).status_code == 403
    csrf = config_de(c.get('/taller-a/visor/'))['csrf']
    r = c.post(API + 'trabajos', json.dumps({'proyecto': pa.pk, 'texto': 'x'}), content_type='application/json',
               HTTP_X_CSRFTOKEN=csrf)
    assert r.status_code == 201
    assert c.get(API + 'trabajos', {'proyecto': pa.pk}).status_code == 200      # leer no pide token


def test_limites_por_plan(ana, t, pa, monkeypatch):
    i = nuevo(ana, pa).json()['id']
    apagadas = set()
    monkeypatch.setattr(api, 'permite', lambda taller, f: f not in apagadas)
    from proyectos import visor
    monkeypatch.setattr(visor, 'permite', lambda taller, f: f not in apagadas)

    apagadas.add('fotos_de_trabajos')
    r = subir_foto(ana, i)
    assert r.status_code == 403 and 'fotos' in r.json()['error']
    assert config_de(ana.get('/taller-a/visor/'))['fotos'] is False
    assert cambiar(ana, i, estado='hecho').status_code == 200

    apagadas.add('trabajos')
    assert nuevo(ana, pa).status_code == 403
    assert cambiar(ana, i, estado='instalado').status_code == 403
    assert ana.delete(f'{API}trabajos/{i}').status_code == 403
    assert len(lista(ana, pa)) == 1                     # se siguen viendo
    assert config_de(ana.get('/taller-a/visor/'))['trabajos'] is False


# ---------------------------------------------------------------- separación entre talleres

@pytest.fixture
def con_trabajos(t, pa, pb):
    t.pa, t.pb = pa, pb
    ta = nuevo(como(t.dueno_a), pa).json()
    tb = nuevo(como(t.dueno_b), pb, base=API_B, texto='trabajo de B').json()
    tb = subir_foto(como(t.dueno_b), tb['id'], base=API_B).json()
    t.trabajo_a, t.trabajo_b, t.foto_b = ta['id'], tb['id'], tb['fotos'][0]
    with con_taller(t.B):
        t.archivo_b = Foto.objects.get().archivo.name
    return t


def test_trabajos_de_b_por_la_direccion_de_a(ana, con_trabajos):
    t = con_trabajos
    assert ana.get(API + 'trabajos', {'proyecto': t.pb.pk}).status_code == 404
    tb, fb = t.trabajo_b, t.foto_b
    for r in (cambiar(ana, tb, texto='cambiado desde A'), cambiar(ana, tb, estado='instalado'),
              ana.delete(f'{API}trabajos/{tb}'), subir_foto(ana, tb),
              ana.delete(f'{API}trabajos/{tb}/fotos/{fb}'),
              ana.delete(f'{API}trabajos/{t.trabajo_a}/fotos/{fb}'),      # foto de B con un trabajo de A
              ana.get(f'{API}fotos/{fb}')):
        assert r.status_code == 404, r.content
    with con_taller(t.B):
        b = Trabajo.objects.get()
        assert (b.texto, b.estado, b.fotos.count()) == ('trabajo de B', 'pendiente', 1)
    assert default_storage.exists(t.archivo_b)


def test_no_se_anota_en_un_proyecto_de_b(ana, con_trabajos):
    t = con_trabajos
    assert nuevo(ana, t.pb).status_code == 404
    with con_taller(t.B):
        assert Trabajo.objects.count() == 1
    with con_taller(t.A), pytest.raises(OtroTaller):
        Trabajo.objects.create(proyecto=t.pb, texto='x')


def test_no_se_asigna_a_alguien_de_b(ana, con_trabajos):
    t = con_trabajos
    assert cambiar(ana, t.trabajo_a, asignado=t.armador_b.pk).status_code == 400


def test_el_equipo_del_visor_es_solo_de_a(ana, con_trabajos):
    nombres = {g['nombre'] for g in config_de(ana.get('/taller-a/visor/'))['equipo']}
    assert nombres == {'Ana', 'Olga', 'Arturo'}


def test_foto_de_b_por_ruta_desde_a(con_trabajos):
    t = con_trabajos
    assert t.archivo_b.startswith(f'talleres/{t.B.pk}/foto/')

    class Pedido:
        taller = t.A
    from django.http import Http404
    with pytest.raises(Http404):
        abrir_de_taller(Pedido(), t.archivo_b)


def test_el_link_del_cliente_no_da_trabajos(client, con_trabajos):
    t = con_trabajos
    link = link_de(t.A, t.pa)
    base = f'/c/{link.codigo}/'
    assert client.get(base).status_code == 200
    assert config_de(client.get(base))['trabajos'] is False
    for r in (client.get(base + 'api/trabajos', {'proyecto': t.pa.pk}),
              client.get(base + 'data/api/trabajos', {'proyecto': t.pa.pk}),
              client.post(base + 'api/trabajos', '{}', content_type='application/json'),
              client.get(f'{base}api/fotos/{t.foto_b}')):
        assert r.status_code == 404
