"""Ficha 03: subir un proyecto, convertirlo en la cola, versiones y biblioteca de materiales.

Las pruebas de error corren el conversor de verdad (en su proceso aparte) con archivos rotos: son instantáneas. Las
que necesitan una conversión que salga bien usan CorrerFalso; la conversión real de las muestras está al final
(marcada `muestras`)."""
import io
import json
from datetime import timedelta
from pathlib import Path

import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image

from proyectos import tareas
from proyectos.models import Material, Original, Proyecto, Version
from talleres.separacion import con_taller
from tests.app.ayudas import DXF_ROTO, DXF_SIN_MUEBLES, MUESTRAS, CorrerFalso, archivos, ocp_real, subir


@pytest.fixture
def falso(monkeypatch):
    f = CorrerFalso()
    monkeypatch.setattr(tareas, 'correr', f)
    return f


@pytest.fixture
def dueno_a(cliente_de, t, django_capture_on_commit_callbacks):
    """Cliente del dueño de A; lo que se encola se ejecuta al confirmar (Huey inmediato)."""
    c = cliente_de(t.dueno_a)
    original = c.post

    def post(*args, **kwargs):
        with django_capture_on_commit_callbacks(execute=True):
            return original(*args, **kwargs)
    c.post = post
    return c


def en_a(t):
    return con_taller(t.A)


def unico_proyecto(t):
    with en_a(t):
        return Proyecto.objects.get()


def version(t, numero=1):
    with en_a(t):
        return Version.objects.get(numero=numero)


def png(color=(150, 100, 60)):
    buf = io.BytesIO()
    Image.new('RGB', (32, 16), color).save(buf, 'PNG')
    return SimpleUploadedFile('roble.png', buf.getvalue(), content_type='image/png')


# ---------------------------------------------------------------- subida

def test_subir_proyecto_guarda_originales_en_la_carpeta_de_la_version(dueno_a, t, falso):
    r = subir(dueno_a, 'taller-a')
    p = unico_proyecto(t)
    assert r.status_code == 302 and r['Location'] == f'/taller-a/proyectos/{p.pk}/'
    assert p.nombre == 'cocina prueba'                         # sin nombre: el del DXF
    v = version(t)
    with en_a(t):
        originales = list(v.originales.all())
    assert sorted(o.tipo for o in originales) == ['dxf', 'ocp']
    for o in originales:
        assert o.archivo.name.startswith(f'talleres/{t.A.pk}/proyectos/{p.pk}/versiones/1/originales/')
        assert o.nombre in ('cocina prueba.dxf', 'cocina prueba.ocp')
    assert falso.llamadas[0]['originales'] == ['cocina prueba.dxf', 'cocina prueba.ocp']   # nombre real


def test_conversion_lista_deja_el_resultado_y_la_version_en_uso(dueno_a, t, falso):
    subir(dueno_a, 'taller-a', nombre='Cocina García')
    v, p = version(t), unico_proyecto(t)
    assert p.nombre == 'Cocina García'
    assert v.estado == 'listo' and v.empezada and v.terminada
    assert p.version_actual_id == v.pk
    carpeta = f'talleres/{t.A.pk}/proyectos/{p.pk}/versiones/1/resultado/'
    assert v.archivo_proyecto == carpeta + 'proyecto.json'
    assert default_storage.exists(carpeta + f'clientes/{p.codigo_cliente}.json')
    assert not default_storage.exists(carpeta + 'materiales.json')
    assert falso.llamadas[0]['entrada']['codigo'] == p.codigo_cliente
    assert v.resumen['proyecto_polyboard'] == 'Falso'


def test_proyecto_dividido_en_varios_ocp(dueno_a, t, falso):
    lista = archivos() + [SimpleUploadedFile('cocina prueba parte 2.ocp', ocp_real())]
    subir(dueno_a, 'taller-a', lista=lista)
    assert len(falso.llamadas[0]['entrada']['ocps']) == 2


@pytest.mark.parametrize('lista,error', [
    (lambda: [SimpleUploadedFile('a.ocp', ocp_real())], 'Falta el DXF 3D'),
    (lambda: [SimpleUploadedFile('a.dxf', DXF_SIN_MUEBLES)], 'Falta la lista de OptiCut'),
    (lambda: archivos() + [SimpleUploadedFile('b.dxf', DXF_SIN_MUEBLES)], 'un solo DXF'),
    (lambda: archivos() + [SimpleUploadedFile('foto.jpg', b'xx')], 'solo se suben'),
    (lambda: archivos(dxf=b'PK\x03\x04 un zip'), 'no es un DXF'),
    (lambda: archivos(ocp=b'cualquier cosa'), 'no parece una lista de OptiCut'),
])
def test_subida_rechazada_con_mensaje(dueno_a, t, falso, lista, error):
    r = subir(dueno_a, 'taller-a', lista=lista())
    assert r.status_code == 400
    assert error in r.content.decode()
    with en_a(t):
        assert not Proyecto.objects.exists() and not Original.objects.exists()
    assert not falso.llamadas


def test_dxf_demasiado_grande(dueno_a, t, settings):
    settings.MAX_DXF_MB = 0
    r = subir(dueno_a, 'taller-a')
    assert r.status_code == 400 and 'el máximo es 0 MB' in r.content.decode()


def test_armador_no_sube_pero_ve_los_proyectos(dueno_a, cliente_de, t, falso, client):
    subir(dueno_a, 'taller-a')
    p = unico_proyecto(t)
    client.logout()
    c = cliente_de(t.armador_a)
    assert c.get('/taller-a/proyectos/nuevo/').status_code == 403
    assert c.post(f'/taller-a/proyectos/{p.pk}/versiones/nueva/', {'archivos': archivos()}).status_code == 403
    assert c.post(f'/taller-a/proyectos/{p.pk}/versiones/1/reconvertir/').status_code == 403
    assert c.get('/taller-a/materiales/').status_code == 403
    lista = c.get('/taller-a/proyectos/')
    assert lista.status_code == 200 and 'cocina prueba' in lista.content.decode()
    assert 'Subir proyecto nuevo' not in lista.content.decode()
    assert c.get(f'/taller-a/proyectos/{p.pk}/').status_code == 200


def test_descargar_original_con_su_nombre(dueno_a, t, falso):
    subir(dueno_a, 'taller-a')
    p = unico_proyecto(t)
    with en_a(t):
        o = Original.objects.get(tipo='ocp')
    r = dueno_a.get(f'/taller-a/proyectos/{p.pk}/versiones/1/originales/{o.pk}/')
    assert b''.join(r.streaming_content) == ocp_real()
    assert 'cocina prueba.ocp' in r['Content-Disposition'] or 'cocina%20prueba.ocp' in r['Content-Disposition']


# ---------------------------------------------------------------- errores de conversión (conversor de verdad)

def test_dxf_sin_muebles_queda_en_error_con_el_mensaje_del_conversor(dueno_a, t):
    subir(dueno_a, 'taller-a', lista=archivos(dxf=DXF_SIN_MUEBLES))
    v = version(t)
    assert v.estado == 'error'
    assert 'no tiene muebles' in v.mensaje and 'Revisá que sea el DXF 3D' in v.mensaje
    assert unico_proyecto(t).version_actual is None
    pagina = dueno_a.get(f'/taller-a/proyectos/{v.proyecto_id}/?ver=versiones').content.decode()
    assert 'No se pudo convertir' in pagina and 'no tiene muebles' in pagina


def test_dxf_roto_queda_en_error_con_mensaje_claro(dueno_a, t):
    subir(dueno_a, 'taller-a', lista=archivos(dxf=DXF_ROTO))
    v = version(t)
    assert v.estado == 'error'
    assert 'Traceback' not in v.mensaje and 'DXF' in v.mensaje


def test_conversion_que_tarda_demasiado_se_corta(dueno_a, t, settings):
    settings.CONVERSION_SEGUNDOS = 0.001
    subir(dueno_a, 'taller-a')
    v = version(t)
    assert v.estado == 'error' and v.mensaje == tareas.TARDO


def test_falla_inesperada_mensaje_generico(dueno_a, t, monkeypatch):
    def rompe(*a):
        raise RuntimeError('detalle técnico')
    monkeypatch.setattr(tareas, 'preparar', rompe)
    subir(dueno_a, 'taller-a')
    v = version(t)
    assert v.estado == 'error' and v.mensaje == tareas.GENERICO


def test_version_cortada_a_mitad_pasa_a_error(dueno_a, t, falso):
    subir(dueno_a, 'taller-a')
    v = version(t)
    with en_a(t):
        Version.objects.filter(pk=v.pk).update(estado='convirtiendo', empezada=timezone.now() - timedelta(hours=2))
    dueno_a.get(f'/taller-a/proyectos/{v.proyecto_id}/')
    v = version(t)
    assert v.estado == 'error' and 'Se cortó' in v.mensaje


def test_pagina_se_actualiza_mientras_convierte(dueno_a, t, falso):
    subir(dueno_a, 'taller-a')
    v = version(t)
    with en_a(t):
        Version.objects.filter(pk=v.pk).update(estado='en_cola')
    assert 'http-equiv="refresh"' in dueno_a.get(f'/taller-a/proyectos/{v.proyecto_id}/?ver=versiones').content.decode()


# ---------------------------------------------------------------- versiones

def test_version_nueva_y_volver_a_la_anterior(dueno_a, t, falso):
    subir(dueno_a, 'taller-a')
    p = unico_proyecto(t)
    r = dueno_a.post(f'/taller-a/proyectos/{p.pk}/versiones/nueva/', {'archivos': archivos()})
    assert r.status_code == 302
    v2 = version(t, 2)
    assert unico_proyecto(t).version_actual_id == v2.pk
    assert default_storage.exists(f'talleres/{t.A.pk}/proyectos/{p.pk}/versiones/2/resultado/proyecto.json')
    assert default_storage.exists(f'talleres/{t.A.pk}/proyectos/{p.pk}/versiones/1/resultado/proyecto.json')

    dueno_a.post(f'/taller-a/proyectos/{p.pk}/versiones/1/usar/')
    assert unico_proyecto(t).version_actual_id == version(t, 1).pk


def test_no_se_usa_una_version_con_error(dueno_a, t):
    subir(dueno_a, 'taller-a', lista=archivos(dxf=DXF_SIN_MUEBLES))
    p = unico_proyecto(t)
    assert dueno_a.post(f'/taller-a/proyectos/{p.pk}/versiones/1/usar/').status_code == 404


def test_volver_a_convertir_crea_otra_version_con_los_mismos_originales(dueno_a, t, falso):
    subir(dueno_a, 'taller-a')
    p = unico_proyecto(t)
    dueno_a.post(f'/taller-a/proyectos/{p.pk}/versiones/1/reconvertir/')
    v1, v2 = version(t, 1), version(t, 2)
    with en_a(t):
        assert ({o.archivo.name for o in v1.originales.all()} == {o.archivo.name for o in v2.originales.all()})
    assert v2.estado == 'listo' and unico_proyecto(t).version_actual_id == v2.pk
    assert falso.llamadas[1]['originales'] == ['cocina prueba.dxf', 'cocina prueba.ocp']


# ---------------------------------------------------------------- materiales

def test_textura_faltante_se_sube_una_vez_y_se_usa_al_volver_a_convertir(dueno_a, t, monkeypatch):
    falso = CorrerFalso(con_imagen={'tableros': {'Roble Kendal': ['Egger\\H1145.jpg', 2800.0]}},
                        avisos=['tablero ROBLE kendal: no se encontró la imagen Egger\\H1145.jpg (.ocp)', 'otro aviso'])
    monkeypatch.setattr(tareas, 'correr', falso)
    subir(dueno_a, 'taller-a')
    v, p = version(t), unico_proyecto(t)
    assert v.faltan_texturas == [{'nombre': 'Roble Kendal', 'tipo': 'tablero'}]
    assert v.avisos == ['otro aviso']                    # el de la imagen se muestra aparte
    with en_a(t):
        m = Material.objects.get()
    assert (m.tipo, m.nombre, m.ruta_polyboard, m.ancho_mm, bool(m.textura)) == (
        'tablero', 'Roble Kendal', 'Egger\\H1145.jpg', 2800, False)
    assert 'tablero Roble Kendal' in dueno_a.get(f'/taller-a/proyectos/{p.pk}/?ver=versiones').content.decode()
    assert 'Roble Kendal' in dueno_a.get('/taller-a/materiales/').content.decode()

    r = dueno_a.post(f'/taller-a/materiales/{m.pk}/', {'nombre': m.nombre, 'textura': png(), 'ancho_mm': '2800', 'color': ''})
    assert r.status_code == 302
    with en_a(t):
        m.refresh_from_db()
    assert m.textura.name.startswith(f'talleres/{t.A.pk}/material/')
    assert dueno_a.get(f'/taller-a/materiales/{m.pk}/imagen/').status_code == 200
    assert 'Subiste texturas que faltaban' in dueno_a.get(f'/taller-a/proyectos/{p.pk}/?ver=versiones').content.decode()

    dueno_a.post(f'/taller-a/proyectos/{p.pk}/versiones/1/reconvertir/')
    llamada = falso.llamadas[1]
    archivo = f'{m.pk}.png'
    assert llamada['materiales'] == {'tableros': {'Roble Kendal': {'textura': archivo, 'ancho': 2800, 'veta': 'n'}},
                                     'cantos': {}}             # png() es lisa: sin veta
    assert llamada['texturas'] == [archivo]
    assert version(t, 2).faltan_texturas == []
    with en_a(t):
        assert Material.objects.count() == 1


def test_tablero_y_canto_con_el_mismo_nombre_no_se_mezclan(dueno_a, t, monkeypatch):
    falso = CorrerFalso(con_imagen={'tableros': {'Roble Kendal': ['Egger\\H1145.jpg', 2800.0]},
                                    'cantos': {'roble kendal': ['Cantos\\roble.jpg', None]}},
                        avisos=['tablero Roble Kendal: no se encontró la imagen Egger\\H1145.jpg (.ocp)',
                                'canto roble kendal: no se encontró la imagen Cantos\\roble.jpg (.ocp)'])
    monkeypatch.setattr(tareas, 'correr', falso)
    subir(dueno_a, 'taller-a')
    v, p = version(t), unico_proyecto(t)
    assert v.faltan_texturas == [{'nombre': 'Roble Kendal', 'tipo': 'tablero'},
                                 {'nombre': 'roble kendal', 'tipo': 'canto'}]
    assert v.avisos == []
    with en_a(t):
        tablero = Material.objects.get(tipo='tablero')
        canto = Material.objects.get(tipo='canto')
    assert (canto.ruta_polyboard, canto.ancho_mm) == ('Cantos\\roble.jpg', None)
    tableros = dueno_a.get('/taller-a/materiales/').content.decode()
    cantos = dueno_a.get('/taller-a/materiales/?ver=cantos').content.decode()
    assert f'/materiales/{tablero.pk}/' in tableros and f'/materiales/{canto.pk}/' not in tableros
    assert f'/materiales/{canto.pk}/' in cantos and f'/materiales/{tablero.pk}/' not in cantos

    # se sube solo la del canto: el tablero sigue faltando y no toma la imagen del canto
    dueno_a.post(f'/taller-a/materiales/{canto.pk}/', {'nombre': canto.nombre, 'textura': png((90, 60, 30)), 'color': ''})
    pagina = dueno_a.get(f'/taller-a/proyectos/{p.pk}/?ver=versiones').content.decode()
    assert 'Subiste texturas que faltaban</strong> (canto roble kendal)' in pagina
    assert 'Faltan texturas:</strong> tablero Roble Kendal' in pagina
    dueno_a.post(f'/taller-a/proyectos/{p.pk}/versiones/1/reconvertir/')
    assert falso.llamadas[1]['materiales'] == {'tableros': {},
                                               'cantos': {'roble kendal': {'textura': f'{canto.pk}.png', 'veta': 'n'}}}
    assert version(t, 2).faltan_texturas == [{'nombre': 'Roble Kendal', 'tipo': 'tablero'}]
    with en_a(t):
        tablero.refresh_from_db()
    assert not tablero.textura


def test_textura_que_no_es_imagen_se_rechaza(dueno_a, t, monkeypatch):
    monkeypatch.setattr(tareas, 'correr', CorrerFalso(con_imagen={'tableros': {'Roble': ['r.jpg', None]}}))
    subir(dueno_a, 'taller-a')
    with en_a(t):
        m = Material.objects.get()
    r = dueno_a.post(f'/taller-a/materiales/{m.pk}/',
                     {'nombre': m.nombre, 'textura': SimpleUploadedFile('roble.jpg', b'no es imagen'), 'color': ''})
    assert r.status_code == 400 and '<span class="error">' in r.content.decode()     # en la ficha, con el error
    with en_a(t):
        m.refresh_from_db()
    assert not m.textura


def rayada(vertical, ancho=64, alto=32):
    im = Image.new('RGB', (ancho, alto))
    for x in range(ancho):
        for y in range(alto):
            im.putpixel((x, y), (200, 150, 100) if ((x if vertical else y) % 8 < 4) else (120, 80, 40))
    buf = io.BytesIO()
    im.save(buf, 'PNG')
    return SimpleUploadedFile('veta.png', buf.getvalue(), content_type='image/png')


def test_veta_detectada_flecha_y_elegida_a_mano(dueno_a, t, monkeypatch):
    falso = CorrerFalso(con_imagen={'tableros': {'Nogal': ['n.jpg', None]}})
    monkeypatch.setattr(tareas, 'correr', falso)
    subir(dueno_a, 'taller-a')
    with en_a(t):
        m = Material.objects.get()
    dueno_a.post(f'/taller-a/materiales/{m.pk}/', {'nombre': m.nombre, 'textura': rayada(vertical=True), 'veta': '', 'color': ''})
    with en_a(t):
        m.refresh_from_db()
    assert (m.veta, m.veta_detectada, m.proporcion) == ('', 'v', 0.5)
    assert 'class="flecha-veta v"' in dueno_a.get('/taller-a/materiales/').content.decode()
    assert 'Vertical (detectada)' in dueno_a.get(f'/taller-a/materiales/{m.pk}/').content.decode()

    # elegida a mano: manda sobre la detectada, avisa volver a convertir, y es la que va al conversor
    r = dueno_a.post(f'/taller-a/materiales/{m.pk}/', {'nombre': m.nombre, 'veta': 'n', 'color': ''}, follow=True)
    assert 'Se guardó la veta de tablero Nogal' in r.content.decode()
    assert 'class="flecha-veta' not in r.content.decode()
    dueno_a.post(f'/taller-a/proyectos/{unico_proyecto(t).pk}/versiones/1/reconvertir/')
    assert falso.llamadas[1]['materiales']['tableros']['Nogal']['veta'] == 'n'


def test_color_del_material_va_al_conversor(dueno_a, t, monkeypatch):
    falso = CorrerFalso(con_imagen={'cantos': {'Grafito': ['g.jpg', None]}})
    monkeypatch.setattr(tareas, 'correr', falso)
    subir(dueno_a, 'taller-a')
    with en_a(t):
        m = Material.objects.get()
    dueno_a.post(f'/taller-a/materiales/{m.pk}/', {'nombre': m.nombre, 'color': '#4c4f52'})
    dueno_a.post(f'/taller-a/proyectos/{unico_proyecto(t).pk}/versiones/1/reconvertir/')
    assert falso.llamadas[1]['materiales'] == {'tableros': {}, 'cantos': {'Grafito': {'color': '#4C4F52'}}}


def test_material_con_color_no_falta(dueno_a, t, monkeypatch):
    monkeypatch.setattr(tareas, 'correr', CorrerFalso(con_imagen={'tableros': {'Gris': ['g.jpg', None]}}))
    subir(dueno_a, 'taller-a')
    p = unico_proyecto(t)
    assert version(t).faltan_texturas == [{'nombre': 'Gris', 'tipo': 'tablero'}]
    assert '1 sin textura' in dueno_a.get('/taller-a/materiales/').content.decode()
    with en_a(t):
        m = Material.objects.get()
    dueno_a.post(f'/taller-a/materiales/{m.pk}/', {'nombre': m.nombre, 'color': '#808080'})
    pagina = dueno_a.get('/taller-a/materiales/').content.decode()
    assert 'sin textura ni color.</strong>' not in pagina and 'class="falta"' not in pagina
    assert 'Faltan texturas' not in dueno_a.get(f'/taller-a/proyectos/{p.pk}/?ver=versiones').content.decode()
    dueno_a.post(f'/taller-a/proyectos/{p.pk}/versiones/1/reconvertir/')
    assert version(t, 2).faltan_texturas == []


# ---------------------------------------------------------------- muestras de verdad, subidas como el navegador

def carpetas_de_muestras():
    return sorted(c for c in MUESTRAS.iterdir() if c.is_dir() and any(c.glob('*.dxf')))


@pytest.mark.muestras
@pytest.mark.parametrize('carpeta', carpetas_de_muestras(), ids=lambda c: c.name)
def test_muestra_subida_desde_el_navegador_queda_lista(dueno_a, t, carpeta):
    lista = [SimpleUploadedFile(f.name, f.read_bytes()) for f in sorted(carpeta.glob('*.dxf')) +
             sorted(carpeta.glob('*.ocp'))]
    r = subir(dueno_a, 'taller-a', lista=lista)
    assert r.status_code == 302
    v = version(t)
    assert v.estado == 'listo', v.mensaje
    esperado = json.loads((carpeta / 'esperado' / 'resumen.json').read_text(encoding='utf-8'))
    for k in ('piezas_ocp', 'paneles', 'con_mecanizado', 'piezas_con_numero', 'vinculados', 'taladros',
              'herrajes', 'muros'):
        assert v.resumen[k] == esperado[k], k
    assert v.resumen['proyecto_polyboard'] == esperado['proyecto']
    with default_storage.open(v.archivo_proyecto) as f:
        datos = json.load(f)
    assert len(datos['paneles']) == esperado['paneles']
    p = unico_proyecto(t)
    assert datos['cliente'] == p.codigo_cliente
    assert default_storage.exists(str(Path(v.archivo_proyecto).parent.as_posix()) + f'/clientes/{p.codigo_cliente}.json')


def test_versiones_viejas_pasan_al_formato_con_tipo(dueno_a, t, falso):
    """Antes de separar tableros y cantos, faltan_texturas era una lista de nombres (migración 0003)."""
    import importlib

    from django.apps import apps
    migracion = importlib.import_module('proyectos.migrations.0003_faltan_texturas_con_tipo')
    subir(dueno_a, 'taller-a')
    v = version(t)
    with en_a(t):
        Version.objects.filter(pk=v.pk).update(faltan_texturas=['Roble'])
    with en_a(t):        # con los modelos de verdad hace falta taller (en la migración no: usa los históricos)
        migracion.con_tipo(apps, None)
    assert version(t).faltan_texturas == [{'nombre': 'Roble', 'tipo': 'tablero'}]
    assert dueno_a.get(f'/taller-a/proyectos/{v.proyecto_id}/').status_code == 200


def test_abm_de_cantos_y_borrar(dueno_a, t):
    r = dueno_a.post('/taller-a/materiales/nuevo-canto/', {'nombre': 'Negro', 'color': '#111111'})
    assert r.status_code == 302 and r['Location'].endswith('?ver=cantos')
    with en_a(t):
        canto = Material.objects.get()
    assert canto.tipo == 'canto'
    assert dueno_a.post('/taller-a/materiales/nuevo-canto/', {'nombre': 'negro', 'color': '#000000'}).status_code == 400
    assert dueno_a.post('/taller-a/materiales/nuevo-otro/', {'nombre': 'X', 'color': '#000000'}).status_code == 404
    ficha = dueno_a.get(f'/taller-a/materiales/{canto.pk}/')
    assert ficha.status_code == 200 and 'Borrar canto' in ficha.content.decode()
    dueno_a.post(f'/taller-a/materiales/{canto.pk}/', {'nombre': 'Negro mate', 'color': '#222222'})
    with en_a(t):
        canto.refresh_from_db()
    assert (canto.nombre, canto.color) == ('Negro mate', '#222222')
    r = dueno_a.post(f'/taller-a/materiales/{canto.pk}/borrar/')
    assert r.status_code == 302 and r['Location'].endswith('?ver=cantos')
    with en_a(t):
        assert not Material.objects.exists()
