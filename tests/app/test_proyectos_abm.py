"""Ficha 22: ABM de proyectos (datos, en desarrollo / en producción, archivar y borrar), la lista con búsqueda y
filtros, y el proyecto en secciones."""
from datetime import date, timedelta

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone

from proyectos.models import LinkCliente, Proyecto
from talleres.separacion import con_taller
from tests.app.ayudas import archivos
from tests.app.test_avance import mueble_chico, post, qr, sin_cache
from tests.app.test_etiquetas import etiqueta, proyecto_de
from tests.app.test_proyectos import dueno_a, falso
from trabajos.models import Trabajo

sin_cache, dueno_a, falso = sin_cache, dueno_a, falso


@pytest.fixture
def pa(t):
    return proyecto_de(t.A)


def archivos_en(carpeta):
    """Los archivos que quedan debajo de la carpeta (las carpetas vacías no cuentan: en R2 no existen)."""
    try:
        carpetas, sueltos = default_storage.listdir(carpeta)
    except FileNotFoundError:
        return []
    return sueltos + [a for c in carpetas for a in archivos_en(f'{carpeta}{c}/')]


def poner(t, p, **campos):
    with con_taller(t.A):
        Proyecto.objects.filter(pk=p.pk).update(**campos)
        p.refresh_from_db()


def test_alta_con_datos_queda_en_desarrollo(dueno_a, t, falso):
    r = dueno_a.post('/taller-a/proyectos/nuevo/', {
        'nombre': 'Placard', 'archivos': archivos(), 'cliente': 'Familia Pérez', 'telefono': '11 5555-0000',
        'mail': 'perez@ejemplo.com', 'direccion': 'Av. Siempreviva 742', 'entrega': '2026-12-01', 'pedido': 'P-120',
        'notas': 'Llamar antes'})
    assert r.status_code == 302
    with con_taller(t.A):
        p = Proyecto.objects.get()
    assert (p.nombre, p.cliente, p.pedido, p.entrega, p.en_produccion) == (
        'Placard', 'Familia Pérez', 'P-120', date(2026, 12, 1), False)
    assert p.en_desarrollo and p.creado_por == t.dueno_a
    # con "Ya va a producción" tildado, entra en producción
    dueno_a.post('/taller-a/proyectos/nuevo/', {'nombre': 'Rack', 'archivos': archivos(), 'en_produccion': 'on'})
    with con_taller(t.A):
        assert Proyecto.objects.get(nombre='Rack').en_produccion


def test_en_desarrollo_no_se_ve_en_produccion(cliente_de, t, pa):
    m = mueble_chico()
    with con_taller(t.A):
        Trabajo.objects.create(proyecto=pa, texto='Cambiar la bisagra')
    c = cliente_de(t.dueno_a)
    assert f'"id": {pa.pk}, "nombre": "{pa.nombre}"' in c.get('/taller-a/puesto/').content.decode()
    assert 'Cambiar la bisagra' in c.get('/taller-a/trabajos/').content.decode()
    c.post(f'/taller-a/proyectos/{pa.pk}/produccion/', {'en_produccion': '0'})
    pa.refresh_from_db()
    assert pa.en_desarrollo
    assert f'"id": {pa.pk}, "nombre": "{pa.nombre}"' not in c.get('/taller-a/puesto/').content.decode()
    assert pa.nombre not in c.get('/taller-a/tablero/').content.decode()
    assert c.get('/taller-a/visor/data/index.json').json() == []
    assert 'Cambiar la bisagra' not in c.get('/taller-a/trabajos/').content.decode()
    # escanear su etiqueta avisa
    d = post(c, '/taller-a/puesto/api/armar', {'texto': qr(etiqueta(t.A, pa, mueble=m))}).json()
    assert d['resultado'] == 'error' and 'en desarrollo' in d['error']
    assert post(c, '/taller-a/puesto/api/cargas/nueva/bulto',
                {'texto': qr(etiqueta(t.A, pa, mueble=m), 1)}).json()['resultado'] == 'error'
    # abierto desde su pantalla (?p=), el visor lo muestra y lee su avance
    lista = c.get(f'/taller-a/visor/data/index.json?p={pa.pk}').json()
    assert [x['id'] for x in lista] == [pa.pk] and 'en desarrollo' in lista[0]['proyecto']
    assert c.get(f'/taller-a/visor/api/avance?proyecto={pa.pk}').status_code == 200
    # habilitarlo lo vuelve a mostrar
    c.post(f'/taller-a/proyectos/{pa.pk}/produccion/', {'en_produccion': '1'})
    assert c.get('/taller-a/visor/data/index.json').json()[0]['id'] == pa.pk


def test_el_link_del_cliente_anda_en_desarrollo(client, t):
    from tests.app.test_visor import proyecto_listo
    p = proyecto_listo(t.A)
    poner(t, p, en_produccion=False)
    with con_taller(t.A):
        link = LinkCliente.objects.create(proyecto=p)
    assert client.get(f'/c/{link.codigo}/').status_code == 200
    assert client.get(f'/c/{link.codigo}/data/cliente.json').status_code == 200


def test_modificar_datos_solo_gestion(cliente_de, t, pa):
    datos = {'nombre': 'Cocina Grondona', 'cliente': 'Grondona', 'telefono': '11 4444', 'mail': 'g@ejemplo.com',
             'direccion': 'Calle 456', 'entrega': '2026-11-15', 'pedido': '77', 'notas': 'Portón angosto'}
    assert cliente_de(t.armador_a).post(f'/taller-a/proyectos/{pa.pk}/datos/', datos).status_code == 403
    cliente_de(t.oficina_a).post(f'/taller-a/proyectos/{pa.pk}/datos/', datos)
    pa.refresh_from_db()
    assert (pa.nombre, pa.direccion, pa.entrega, pa.notas) == ('Cocina Grondona', 'Calle 456', date(2026, 11, 15),
                                                                'Portón angosto')
    r = cliente_de(t.oficina_a).post(f'/taller-a/proyectos/{pa.pk}/datos/', {**datos, 'mail': 'no es un mail'},
                                     follow=True)
    assert 'Revisá los datos' in r.content.decode()
    # el armador los ve, sin formulario
    html = cliente_de(t.armador_a).get(f'/taller-a/proyectos/{pa.pk}/').content.decode()
    assert 'Portón angosto' in html and 'name="pedido"' not in html


def test_archivar_desarchivar_y_borrar(cliente_de, t, pa):
    assert cliente_de(t.armador_a).post(f'/taller-a/proyectos/{pa.pk}/archivar/').status_code == 403
    c = cliente_de(t.oficina_a)             # el cliente de las pruebas es uno solo: cambia de persona
    c.post(f'/taller-a/proyectos/{pa.pk}/archivar/')
    pa.refresh_from_db()
    assert pa.archivado_en and pa.archivado_por == t.oficina_a and pa.estado == 'archivado'
    tarjeta = f'proyectos/{pa.pk}/"'
    assert tarjeta not in c.get('/taller-a/proyectos/').content.decode()
    assert tarjeta in c.get('/taller-a/proyectos/?estado=archivados').content.decode()
    assert f'"nombre": "{pa.nombre}"' not in c.get('/taller-a/puesto/').content.decode()
    # no se habilita mientras está archivado; se desarchiva
    assert c.post(f'/taller-a/proyectos/{pa.pk}/produccion/', {'en_produccion': '1'}).status_code == 404
    c.post(f'/taller-a/proyectos/{pa.pk}/desarchivar/')
    pa.refresh_from_db()
    assert pa.archivado_en is None and pa.en_produccion
    # borrar: solo el dueño, solo archivado y con el nombre bien escrito
    c.post(f'/taller-a/proyectos/{pa.pk}/archivar/')
    assert c.post(f'/taller-a/proyectos/{pa.pk}/borrar/', {'nombre': pa.nombre}).status_code == 403
    c.post(f'/taller-a/proyectos/{pa.pk}/desarchivar/')
    d = cliente_de(t.dueno_a)
    assert d.post(f'/taller-a/proyectos/{pa.pk}/borrar/', {'nombre': pa.nombre}).status_code == 404
    d.post(f'/taller-a/proyectos/{pa.pk}/archivar/')
    d.post(f'/taller-a/proyectos/{pa.pk}/borrar/', {'nombre': 'otro'})
    with con_taller(t.A):
        assert Proyecto.objects.filter(pk=pa.pk).exists()
        v = pa.version_actual
        carpeta = v.carpeta()
        foto = default_storage.save(f'talleres/{t.A.pk}/foto/x_foto.jpg', ContentFile(b'jpg'))
        tarea = Trabajo.objects.create(proyecto=pa, texto='x')
        tarea.fotos.create(archivo=foto, tamano=3)
    assert default_storage.exists(v.archivo_proyecto)
    r = d.post(f'/taller-a/proyectos/{pa.pk}/borrar/', {'nombre': ' COCINA grondona '})
    assert r.status_code == 302 and 'estado=archivados' in r['Location']
    with con_taller(t.A):
        assert not Proyecto.objects.filter(pk=pa.pk).exists() and not Trabajo.objects.exists()
    assert not default_storage.exists(v.archivo_proyecto) and not default_storage.exists(foto)
    assert archivos_en(carpeta) == []


def test_lista_busca_y_filtra(cliente_de, t, pa):
    otro = proyecto_de(t.A, nombre='rack living')
    poner(t, otro, en_produccion=False, pedido='P-9', entrega=timezone.localdate() - timedelta(days=3))
    c = cliente_de(t.armador_a)
    html = c.get('/taller-a/proyectos/').content.decode()
    assert 'cocina grondona' in html and 'rack living' in html and 'vencida' in html
    html = c.get('/taller-a/proyectos/?estado=desarrollo').content.decode()
    assert 'rack living' in html and 'cocina grondona' not in html
    html = c.get('/taller-a/proyectos/?estado=produccion').content.decode()
    assert 'cocina grondona' in html and 'rack living' not in html
    html = c.get('/taller-a/proyectos/?q=p-9').content.decode()
    assert 'rack living' in html and 'cocina grondona' not in html
    assert 'cocina grondona' in c.get('/taller-a/proyectos/?q=Grondona').content.decode()   # por cliente


def test_secciones_del_proyecto(cliente_de, t, pa):
    c = cliente_de(t.dueno_a)
    for ver, texto in (('', 'Datos del proyecto'), ('produccion', 'Avance por mueble'),
                       ('cliente', 'Link para el cliente'), ('versiones', 'Subir versión nueva'),
                       ('cualquiera', 'Datos del proyecto')):
        html = c.get(f'/taller-a/proyectos/{pa.pk}/?ver={ver}').content.decode()
        assert texto in html and 'aria-current="page"' in html


def test_desde_b_no_se_toca_nada_de_a(cliente_de, t, pa):
    cb = cliente_de(t.dueno_b)
    for accion, datos in (('datos', {'nombre': 'x'}), ('produccion', {'en_produccion': '0'}), ('archivar', {}),
                          ('desarchivar', {}), ('borrar', {'nombre': pa.nombre})):
        assert cb.post(f'/taller-b/proyectos/{pa.pk}/{accion}/', datos).status_code == 404
    assert pa.nombre not in cb.get('/taller-b/proyectos/?estado=todos').content.decode()
    pa.refresh_from_db()
    assert pa.en_produccion and pa.archivado_en is None


def test_la_lista_recuerda_los_filtros(cliente_de, t, pa):
    c = cliente_de(t.armador_a)
    assert c.get('/taller-a/proyectos/').status_code == 200                 # la primera vez, sin nada guardado
    c.get('/taller-a/proyectos/?estado=desarrollo&q=coc')
    r = c.get('/taller-a/proyectos/')                                         # al volver (desde un proyecto, el menú…)
    assert r.status_code == 302 and 'estado=desarrollo' in r['Location'] and 'q=coc' in r['Location']
    c.get('/taller-a/proyectos/?estado=')                                     # "En curso" y sin buscar
    assert c.get('/taller-a/proyectos/')['Location'].endswith('?estado=')
