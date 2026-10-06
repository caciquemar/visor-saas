"""Ficha 04: el visor servido por la app (/<taller>/visor/) y el link del cliente (/c/<código>/).

Los proyectos se arman a mano con un resultado mínimo en el almacenamiento (como lo deja la conversión): no hace
falta correr el conversor para probar quién puede ver qué."""
import io
import json
import re
from datetime import timedelta

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image

from proyectos.models import LinkCliente, Proyecto, Version
from proyectos.visor import INDEX
from talleres.formularios import luminancia
from talleres.separacion import OtroTaller, con_taller

PROYECTO = {'proyecto': 'Cocina', 'paneles': [{'num': '0053', 'pieza': '2', 'mueble': 'Bajo', 'mat': 'Roble'}],
            'materiales': {'Roble': {'textura': 'texturas/1-abc.jpg'}}, 'cliente': 'x'}
CLIENTE = {'proyecto': 'Cocina', 'paneles': [{'mueble': 'Bajo', 'mat': 'Roble'}],
           'materiales': {'Roble': {'textura': 'texturas/1-abc.jpg'}}, 'ar': {'': 'CC/todo.glb'}}


def proyecto_listo(taller, nombre='Cocina', estado=Version.Estado.LISTO):
    """Proyecto con una versión convertida: resultado/proyecto.json, clientes/<cc>.json, un GLB y una textura."""
    with con_taller(taller):
        p = Proyecto.objects.create(nombre=nombre)
        v = Version.objects.create(proyecto=p, numero=1, estado=estado)
        base = f'{v.carpeta()}resultado/'
        cc = p.codigo_cliente
        cliente = json.loads(json.dumps(CLIENTE).replace('CC/', f'{cc}/'))
        archivos = {'proyecto.json': json.dumps({**PROYECTO, 'proyecto': nombre, 'cliente': cc}),
                    f'clientes/{cc}.json': json.dumps(cliente),
                    f'clientes/{cc}/todo.glb': b'glTF-falso',
                    'texturas/1-abc.jpg': b'jpg-falso'}
        for ruta, contenido in archivos.items():
            default_storage.save(base + ruta, ContentFile(contenido.encode() if isinstance(contenido, str)
                                                          else contenido))
        v.archivo_proyecto = base + 'proyecto.json'
        v.save()
        p.version_actual = v
        p.save()
    return p


def link_de(taller, proyecto, **campos):
    with con_taller(taller):
        return LinkCliente.objects.create(proyecto=proyecto, **campos)


def config_de(r):
    """La configuración que la app puso en window.VISOR."""
    m = re.search(r'window\.VISOR = (.*?);\n', r.content.decode())
    return json.loads(m.group(1))


@pytest.fixture
def pa(t):
    return proyecto_listo(t.A)


@pytest.fixture
def pb(t):
    return proyecto_listo(t.B, nombre='Placard de B')


# ---------------------------------------------------------------- visor del taller

def test_visor_pide_login(client, t):
    r = client.get('/taller-a/visor/')
    assert r.status_code == 302 and r['Location'].startswith('/entrar/')
    assert client.get('/taller-a/visor/data/index.json').status_code == 302


def test_visor_es_el_index_html_con_la_configuracion(cliente_de, t):
    r = cliente_de(t.armador_a).get('/taller-a/visor/')
    assert r.status_code == 200
    original = INDEX.read_text(encoding='utf-8')
    html = r.content.decode()
    config = config_de(r)
    assert config == {'trabajos': False, 'marca': {'nombre': 'Taller A'}}
    # nada más cambia: así el visor no se separa de visor/index.html
    assert html.replace(json.dumps(config, ensure_ascii=False), '/*__VISOR__*/null') == original
    assert 'Nord Good' not in html
    assert r['Cache-Control'] == 'no-cache'


def test_la_configuracion_no_puede_cerrar_el_script(cliente_de, t):
    t.A.nombre = 'Taller </script><script>alert(1)</script>'
    t.A.save()
    html = cliente_de(t.dueno_a).get('/taller-a/visor/').content.decode()
    assert '</script><script>alert(1)' not in html


def test_indice_lista_solo_proyectos_listos_del_taller(cliente_de, t, pa, pb):
    proyecto_listo(t.A, nombre='En cola', estado=Version.Estado.EN_COLA)
    r = cliente_de(t.armador_a).get('/taller-a/visor/data/index.json')
    assert r.json() == [{'id': pa.pk, 'proyecto': 'Cocina', 'archivo': f'{pa.pk}/proyecto.json', 'link': None}]


def test_indice_trae_el_link_vigente_mas_nuevo(cliente_de, t, pa):
    link_de(t.A, pa, anulado=timezone.now())
    link_de(t.A, pa, vence=timezone.now() - timedelta(days=1))
    bueno = link_de(t.A, pa)
    lista = cliente_de(t.dueno_a).get('/taller-a/visor/data/index.json').json()
    assert lista[0]['link'] == f'http://testserver/c/{bueno.codigo}/'


def test_datos_del_proyecto_y_texturas(cliente_de, t, pa):
    c = cliente_de(t.armador_a)
    r = c.get(f'/taller-a/visor/data/{pa.pk}/proyecto.json')
    assert r.status_code == 200 and json.loads(b''.join(r.streaming_content))['paneles'][0]['num'] == '0053'
    assert r['Cache-Control'] == 'no-cache'
    r = c.get(f'/taller-a/visor/data/{pa.pk}/texturas/1-abc.jpg')
    assert r.status_code == 200 and 'max-age' in r['Cache-Control']
    assert c.get('/taller-a/visor/data/materiales.json').json() == {}


def test_proyecto_de_b_por_el_visor_de_a(cliente_de, t, pa, pb):
    c = cliente_de(t.dueno_a)
    for ruta in ('proyecto.json', 'texturas/1-abc.jpg', f'clientes/{pb.codigo_cliente}.json'):
        assert c.get(f'/taller-a/visor/data/{pb.pk}/{ruta}').status_code == 404
    # y el usuario de A no entra al visor de B
    assert c.get('/taller-b/visor/data/index.json').status_code == 404
    assert c.get(f'/taller-b/visor/data/{pb.pk}/proyecto.json').status_code == 404


@pytest.mark.parametrize('ruta', ['../2/proyecto.json', '..%2F..%2Foriginales/x.dxf', 'texturas/../../originales/a',
                                  'x/../../../../../talleres/2/material/a.jpg', 'no-existe.json'])
def test_rutas_raras_en_el_visor(cliente_de, t, pa, ruta):
    assert cliente_de(t.dueno_a).get(f'/taller-a/visor/data/{pa.pk}/{ruta}').status_code == 404


def test_manifest_generico(cliente_de, t):
    m = json.loads(cliente_de(t.armador_a).get('/taller-a/visor/manifest.webmanifest').content)
    assert m['name'] == 'Visor' and m['start_url'] == '/taller-a/visor/'
    assert all(i['src'].startswith('/static/visor/') for i in m['icons'])


# ---------------------------------------------------------------- link del cliente

def test_link_abre_sin_login_con_la_marca_del_taller(client, t, pa, settings):
    settings.MARCA_SERVICIO = 'Visor'
    t.A.color = '#2F6F5E'
    t.A.save()
    link = link_de(t.A, pa)
    r = client.get(f'/c/{link.codigo}/')
    assert r.status_code == 200
    config = config_de(r)
    assert config['cliente'] is True and config['trabajos'] is False
    assert config['marca'] == {'nombre': 'Taller A', 'color': '#2F6F5E', 'logo': None}
    assert config['pie']['nombre'] == 'Visor'
    assert r['Referrer-Policy'] == 'no-referrer'


def test_link_sirve_solo_la_version_cliente(client, t, pa):
    link = link_de(t.A, pa)
    base = f'/c/{link.codigo}/data/'
    r = client.get(base + 'cliente.json')
    datos = json.loads(b''.join(r.streaming_content))
    assert r.status_code == 200 and 'num' not in datos['paneles'][0] and 'pieza' not in datos['paneles'][0]
    assert client.get(base + f'clientes/{pa.codigo_cliente}/todo.glb')['Content-Type'] == 'model/gltf-binary'
    assert client.get(base + 'texturas/1-abc.jpg').status_code == 200
    assert client.get(base + 'materiales.json').json() == {}


@pytest.mark.parametrize('ruta', ['proyecto.json', '../proyecto.json', 'clientes/../proyecto.json', 'index.json',
                                  'clientes/OTRO/todo.glb', 'texturas/../proyecto.json', 'x/proyecto.json'])
def test_link_no_da_el_proyecto_del_taller(client, t, pa, ruta):
    link = link_de(t.A, pa)
    assert client.get(f'/c/{link.codigo}/data/{ruta}').status_code == 404


def test_link_no_da_nada_del_resto_del_taller(client, t, pa):
    otro = proyecto_listo(t.A, nombre='Otro de A')
    link = link_de(t.A, pa)
    assert client.get(f'/c/{link.codigo}/data/clientes/{otro.codigo_cliente}/todo.glb').status_code == 404
    assert client.get(f'/taller-a/visor/data/{pa.pk}/proyecto.json').status_code == 302     # pide entrar


def test_link_de_b_no_abre_cosas_de_a(client, t, pa, pb):
    link_b = link_de(t.B, pb)
    assert client.get(f'/c/{link_b.codigo}/data/clientes/{pa.codigo_cliente}/todo.glb').status_code == 404
    datos = json.loads(b''.join(client.get(f'/c/{link_b.codigo}/data/cliente.json').streaming_content))
    assert datos['proyecto'] == 'Cocina' and pb.codigo_cliente in datos['ar']['']     # el de B, no el de A


def test_visitas_cuentan_la_pagina_y_no_los_archivos_ni_al_taller(client, cliente_de, t, pa):
    link = link_de(t.A, pa)
    client.get(f'/c/{link.codigo}/')
    client.get(f'/c/{link.codigo}/')
    client.get(f'/c/{link.codigo}/data/cliente.json')
    cliente_de(t.dueno_a).get(f'/c/{link.codigo}/')           # "Ver como cliente" desde el taller
    with con_taller(t.A):
        link.refresh_from_db()
    assert link.visitas == 2 and link.ultima_visita is not None


@pytest.mark.parametrize('campos', [{'anulado': timezone.now()}, {'vence': timezone.now() - timedelta(minutes=1)}],
                         ids=['anulado', 'vencido'])
def test_link_anulado_o_vencido_no_anda(client, t, pa, campos):
    link = link_de(t.A, pa, **campos)
    r = client.get(f'/c/{link.codigo}/')
    assert r.status_code == 404 and 'ya no está disponible' in r.content.decode()
    assert 'Taller A' not in r.content.decode()
    for ruta in ('cliente.json', f'clientes/{pa.codigo_cliente}/todo.glb', 'texturas/1-abc.jpg'):
        assert client.get(f'/c/{link.codigo}/data/{ruta}').status_code == 404


def test_codigo_inventado_o_del_conversor_no_abre(client, t, pa):
    link_de(t.A, pa)
    for codigo in ('inventado', pa.codigo_cliente):
        r = client.get(f'/c/{codigo}/')
        assert r.status_code == 404 and 'Taller A' not in r.content.decode()


def test_link_de_taller_inactivo_no_anda(client, t, pa):
    link = link_de(t.A, pa)
    t.A.activo = False
    t.A.save()
    assert client.get(f'/c/{link.codigo}/').status_code == 404


def test_link_sin_version_lista(client, t):
    p = proyecto_listo(t.A, estado=Version.Estado.ERROR)
    link = link_de(t.A, p)
    assert client.get(f'/c/{link.codigo}/').status_code == 404


def test_codigo_no_adivinable(t, pa):
    codigos = {link_de(t.A, pa).codigo for _ in range(5)}
    assert len(codigos) == 5 and all(len(c) >= 21 for c in codigos)


# ---------------------------------------------------------------- crear y anular

def test_dueno_crea_y_anula_el_link(client, cliente_de, t, pa):
    c = cliente_de(t.oficina_a)
    r = c.post(f'/taller-a/proyectos/{pa.pk}/links/nuevo/', {'dias': '30'})
    assert r.status_code == 302
    with con_taller(t.A):
        link = LinkCliente.objects.get()
    assert link.creado_por == t.oficina_a
    assert timedelta(days=29) < link.vence - timezone.now() <= timedelta(days=30)
    pagina = c.get(f'/taller-a/proyectos/{pa.pk}/').content.decode()
    assert f'/c/{link.codigo}/' in pagina

    c.post(f'/taller-a/proyectos/{pa.pk}/links/{link.pk}/anular/')
    client.logout()
    assert client.get(f'/c/{link.codigo}/').status_code == 404


def test_link_que_no_vence(cliente_de, t, pa):
    cliente_de(t.dueno_a).post(f'/taller-a/proyectos/{pa.pk}/links/nuevo/', {'dias': '0'})
    with con_taller(t.A):
        assert LinkCliente.objects.get().vence is None


def test_vencimiento_invalido(cliente_de, t, pa):
    cliente_de(t.dueno_a).post(f'/taller-a/proyectos/{pa.pk}/links/nuevo/', {'dias': '9999'})
    with con_taller(t.A):
        assert not LinkCliente.objects.exists()


def test_armador_no_crea_ni_anula_links(cliente_de, t, pa):
    link = link_de(t.A, pa)
    c = cliente_de(t.armador_a)
    assert c.post(f'/taller-a/proyectos/{pa.pk}/links/nuevo/', {'dias': '30'}).status_code == 403
    assert c.post(f'/taller-a/proyectos/{pa.pk}/links/{link.pk}/anular/').status_code == 403


def test_no_se_anula_un_link_de_b_desde_a(cliente_de, t, pa, pb):
    link_b = link_de(t.B, pb)
    c = cliente_de(t.dueno_a)
    assert c.post(f'/taller-a/proyectos/{pb.pk}/links/{link_b.pk}/anular/').status_code == 404
    assert c.post(f'/taller-a/proyectos/{pa.pk}/links/{link_b.pk}/anular/').status_code == 404
    assert c.post(f'/taller-a/proyectos/{pb.pk}/links/nuevo/', {'dias': '30'}).status_code == 404
    with con_taller(t.B):
        link_b.refresh_from_db()
    assert link_b.anulado is None


def test_link_no_se_cruza_de_taller(t, pa, pb):
    with con_taller(t.A):
        assert not LinkCliente.objects.filter(pk=link_de(t.B, pb).pk).exists()
        with pytest.raises(OtroTaller):
            LinkCliente.objects.create(proyecto=pb)


# ---------------------------------------------------------------- marca

def imagen(formato='PNG', nombre='logo.png'):
    buf = io.BytesIO()
    Image.new('RGB', (60, 20), (20, 40, 90)).save(buf, formato)
    return SimpleUploadedFile(nombre, buf.getvalue())


def test_dueno_carga_logo_y_color_y_el_link_los_muestra(client, cliente_de, t, pa):
    c = cliente_de(t.dueno_a)
    r = c.post('/taller-a/marca/', {'color': '#2f6f5e', 'logo': imagen()})
    assert r.status_code == 302
    t.A.refresh_from_db()
    assert t.A.color == '#2F6F5E' and t.A.logo.name.startswith(f'talleres/{t.A.pk}/marca/')
    assert c.get('/taller-a/marca/logo/').status_code == 200

    link = link_de(t.A, pa)
    client.logout()
    assert config_de(client.get(f'/c/{link.codigo}/'))['marca']['logo'] == 'logo'
    assert client.get(f'/c/{link.codigo}/logo').status_code == 200


def test_cambiar_el_color_conserva_el_logo(cliente_de, t):
    c = cliente_de(t.dueno_a)
    c.post('/taller-a/marca/', {'logo': imagen()})
    assert c.post('/taller-a/marca/', {'color': '#2F6F5E'}).status_code == 302
    t.A.refresh_from_db()
    assert t.A.logo and t.A.color == '#2F6F5E'
    assert c.post('/taller-a/marca/', {'color': '#2F6F5E', 'quitar_logo': 'on'}).status_code == 302
    t.A.refresh_from_db()
    assert not t.A.logo


def test_logo_y_color_invalidos(cliente_de, t):
    c = cliente_de(t.dueno_a)
    svg = SimpleUploadedFile('logo.svg', b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')
    assert c.post('/taller-a/marca/', {'logo': svg}).status_code == 400
    assert c.post('/taller-a/marca/', {'color': '#FFFF66'}).status_code == 400          # muy claro
    assert c.post('/taller-a/marca/', {'color': 'red'}).status_code == 400
    t.A.refresh_from_db()
    assert not t.A.logo and not t.A.color


def test_solo_el_dueno_cambia_la_marca(cliente_de, t):
    assert cliente_de(t.oficina_a).get('/taller-a/marca/').status_code == 403


def test_link_no_da_el_logo_de_otro_taller(client, t, pb):
    t.A.logo.save('logo.png', imagen(), save=True)
    link_b = link_de(t.B, pb)
    assert client.get(f'/c/{link_b.codigo}/logo').status_code == 404       # B no tiene logo; el de A no sale


def test_luminancia():
    assert luminancia('#000000') == 0 and luminancia('#FFFFFF') == pytest.approx(1)
    assert luminancia('#1D5FE0') < .4 < luminancia('#FFFF66')
