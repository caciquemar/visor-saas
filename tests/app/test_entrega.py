"""Ficha 18: del armado a la instalación (armado por mueble, control de calidad, instalación, Lista y 3D de entrega).

Con el proyecto.json real de *cocina grondona*, como test_avance.py."""
import json

import pytest
from django.utils import timezone

from avance import pasos as pasos_
from avance.models import (Bulto, Carga, Control, FotoDeInstalacion, Instalacion, PuntoDeControl, Ubicado,
                           puntos_de_control)
from talleres.separacion import OtroTaller, con_taller
from tests.app.test_avance import (etapas, marcar, marcar_todas, mueble_chico, piezas_del, post, qr, sin_cache,
                                   terminar, ubicaciones)
from tests.app.test_etiquetas import etiqueta, proyecto_de

sin_cache = sin_cache


@pytest.fixture
def pa(t):
    return proyecto_de(t.A)


def paso(taller, proyecto, mueble):
    with con_taller(taller):
        return pasos_.pasos(proyecto)['muebles'][mueble]


# ---------------------------------------------------------------- paso de cada mueble

def test_pasos_de_un_mueble_hasta_cargado(cliente_de, t, pa):
    m = mueble_chico()
    assert paso(t.A, pa, m)['paso'] == 'sin_armar'
    marcar_todas(t.A, pa, m, etapas(t.A)['Armada'])
    assert paso(t.A, pa, m)['paso'] == 'armado'
    with con_taller(t.A):
        Control.objects.create(proyecto=pa, mueble=m, resultados=[], cuando=timezone.now())
    assert paso(t.A, pa, m)['paso'] == 'controlado'
    c = cliente_de(t.armador_a)
    terminar(c, pa, m, 2, 'prueba')
    assert paso(t.A, pa, m)['paso'] == 'embalado'
    c.post(f'/taller-a/proyectos/{pa.pk}/cargas/nueva/', {'todo': '1'})
    with con_taller(t.A):
        carga = Carga.objects.get()
    post(c, f'/taller-a/puesto/api/cargas/{carga.pk}/bulto', {'texto': qr(etiqueta(t.A, pa, mueble=m), 1)})
    d = paso(t.A, pa, m)
    assert d['paso'] == 'cargado' and d['bultos'] == {'total': 2, 'cargados': 1, 'entregados': 0}


# ---------------------------------------------------------------- puntos de control (Procesos)

def test_puntos_de_control_por_defecto_y_solo_el_dueno(cliente_de, t):
    with con_taller(t.A):
        assert [p.nombre for p in puntos_de_control()] == ['Cantos', 'Todas las piezas', 'Frentes', 'Herrajes']
    dueno = cliente_de(t.dueno_a)
    assert 'Control de calidad' in dueno.get('/taller-a/procesos/').content.decode()
    dueno.post('/taller-a/procesos/', {'accion': 'agregar-puntos', 'nombre': 'Limpieza'})
    with con_taller(t.A):
        assert PuntoDeControl.objects.last().nombre == 'Limpieza'
    oficina = cliente_de(t.oficina_a)
    assert 'Control de calidad' not in oficina.get('/taller-a/procesos/').content.decode()
    assert oficina.post('/taller-a/procesos/', {'accion': 'agregar-puntos', 'nombre': 'X'}).status_code == 403
    with con_taller(t.B):
        assert 'Limpieza' not in [p.nombre for p in puntos_de_control()]


def test_modelos_de_entrega_no_se_cruzan(t, pa):
    with con_taller(t.A):
        i = Instalacion.objects.create(proyecto=pa, mueble='x', cuando=timezone.now())
        Control.objects.create(proyecto=pa, mueble='x', cuando=timezone.now())
    with con_taller(t.B):
        for modelo in (Instalacion, Control, FotoDeInstalacion):
            assert not modelo.objects.exists(), modelo
        with pytest.raises(OtroTaller):
            Control.objects.create(proyecto=pa, mueble='y', cuando=timezone.now())
        with pytest.raises(OtroTaller):
            Instalacion.objects.create(proyecto=pa, mueble='y', cuando=timezone.now())
        with pytest.raises(OtroTaller):
            FotoDeInstalacion.objects.create(instalacion=i, archivo='x.jpg')


# ---------------------------------------------------------------- armado del mueble entero

def test_armar_el_mueble_desde_una_pieza_y_deshacer(cliente_de, t, pa):
    from avance.models import Marca
    estante, = ubicaciones(t.A, 'Estante A')
    m = mueble_chico()
    piezas = piezas_del(m)
    c = cliente_de(t.armador_a)
    marcar(c, etiqueta(t.A, pa, piezas[0]).codigo, etapas(t.A)['Armada'])       # una ya estaba armada
    d = post(c, '/taller-a/puesto/api/armar', {'texto': etiqueta(t.A, pa, piezas[1]).codigo,
                                               'ubicacion': estante.pk}).json()
    assert d['resultado'] == 'ok' and d['mueble'] == m and d['piezas'] == len(piezas)
    assert d['nuevas'] == len(piezas) - 1 and len(d['marcas']) == len(piezas) - 1 and d['ubicacion'] == 'Estante A'
    assert paso(t.A, pa, m)['paso'] == 'armado'
    with con_taller(t.A):
        assert Ubicado.objects.filter(ubicacion=estante).count() == len(piezas)
    # otra vez: ya estaba
    assert post(c, '/taller-a/puesto/api/armar', {'texto': qr(etiqueta(t.A, pa, mueble=m))}).json()['resultado'] == 'ya'
    # deshacer saca las que marcó (no la que ya estaba)
    assert post(c, '/taller-a/puesto/api/deshacer', {'marcas': d['marcas']}).json()['deshechas'] == len(piezas) - 1
    with con_taller(t.A):
        assert Marca.objects.filter(deshecha_en__isnull=True, mueble=m).count() == 1
    assert paso(t.A, pa, m)['paso'] == 'sin_armar'
    assert post(c, '/taller-a/puesto/api/deshacer', {'marcas': ['x']}).status_code == 400


def test_etiqueta_del_mueble_sin_bulto(cliente_de, t, pa):
    m = mueble_chico()
    r = cliente_de(t.armador_a).get('/taller-a/visor/api/etiquetas/pdf', {'proyecto': pa.pk, 'm': m, 'bultos': 0})
    assert r.status_code == 200 and r['Content-Type'] == 'application/pdf'


# ---------------------------------------------------------------- control de calidad

def test_control_con_un_punto_mal_crea_la_tarea_y_deja_embalar(cliente_de, t, pa):
    from trabajos.models import Trabajo
    m = mueble_chico()
    c = cliente_de(t.armador_a)
    marcar_todas(t.A, pa, m, etapas(t.A)['Armada'])
    d = post(c, '/taller-a/puesto/api/control', {'texto': qr(etiqueta(t.A, pa, mueble=m))}).json()
    assert d['armado'] and [p['nombre'] for p in d['puntos']] == ['Cantos', 'Todas las piezas', 'Frentes', 'Herrajes']
    assert d['ultimo'] is None
    ids = {p['nombre']: p['id'] for p in d['puntos']}
    incompleto = [{'punto': ids['Cantos'], 'ok': True}]
    r = post(c, '/taller-a/puesto/api/control', {'proyecto': pa.pk, 'mueble': m, 'resultados': incompleto})
    assert r.status_code == 400 and 'Falta revisar' in r.json()['error']
    resultados = [{'punto': i, 'ok': n != 'Frentes', 'nota': 'Rayado' if n == 'Frentes' else ''} for n, i in ids.items()]
    d = post(c, '/taller-a/puesto/api/control', {'proyecto': pa.pk, 'mueble': m, 'resultados': resultados}).json()
    assert d['control']['ok'] is False and d['control']['mal'] == ['Frentes'] and len(d['tareas']) == 1
    with con_taller(t.A):
        tarea = Trabajo.objects.get(pk=d['tareas'][0])
        assert tarea.texto == 'Control de calidad · Frentes: Rayado' and tarea.muebles == [m] and tarea.autor == t.armador_a
    assert paso(t.A, pa, m)['paso'] == 'controlado'
    # se embala igual, y el embalaje muestra el control
    assert terminar(c, pa, m, 1).json()['control']['mal'] == ['Frentes']
    assert paso(t.A, pa, m)['paso'] == 'embalado'


# ---------------------------------------------------------------- instalación en obra

def entregar_todo(c, t, pa, m, bultos=1):
    terminar(c, pa, m, bultos, 'prueba')
    c.post(f'/taller-a/proyectos/{pa.pk}/cargas/nueva/', {'todo': '0', 'mueble': [m]})
    with con_taller(t.A):
        carga = Carga.objects.last()
    e = etiqueta(t.A, pa, mueble=m)
    for n in range(1, bultos + 1):
        post(c, f'/taller-a/puesto/api/cargas/{carga.pk}/bulto', {'texto': qr(e, n)})
    c.post(f'/taller-a/cargas/{carga.pk}/', {'motivo': ''})
    for n in range(1, bultos + 1):
        post(c, f'/taller-a/puesto/api/cargas/{carga.pk}/bulto', {'texto': qr(e, n), 'entregar': True})


def test_instalar_sin_faltantes_y_deshacer_solo_gestion(cliente_de, t, pa):
    m = mueble_chico()
    c = cliente_de(t.armador_a)
    entregar_todo(c, t, pa, m)
    assert paso(t.A, pa, m)['paso'] == 'entregado'
    d = post(c, '/taller-a/puesto/api/instalacion', {'texto': qr(etiqueta(t.A, pa, mueble=m), 1)}).json()
    assert d['faltan'] == [] and d['bultos'] == {'total': 1, 'cargados': 1, 'entregados': 1} and d['instalacion'] is None
    d = post(c, '/taller-a/puesto/api/instalar', {'proyecto': pa.pk, 'mueble': m, 'nota': 'Quedó nivelado'}).json()
    assert d['instalacion']['nota'] == 'Quedó nivelado' and d['instalacion']['por'] == 'Arturo'
    assert paso(t.A, pa, m)['paso'] == 'instalado'
    assert post(c, '/taller-a/puesto/api/instalar', {'proyecto': pa.pk, 'mueble': m}).status_code == 409
    assert post(c, '/taller-a/puesto/api/desinstalar', {'proyecto': pa.pk, 'mueble': m}).status_code == 403
    assert post(cliente_de(t.oficina_a), '/taller-a/puesto/api/desinstalar',
                {'proyecto': pa.pk, 'mueble': m}).json()['resultado'] == 'ok'
    assert paso(t.A, pa, m)['paso'] == 'entregado'


def test_instalar_con_faltantes_pide_motivo(cliente_de, t, pa):
    from trabajos.models import Trabajo
    m = mueble_chico()
    c = cliente_de(t.armador_a)
    terminar(c, pa, m, 2, 'prueba')
    with con_taller(t.A):
        Trabajo.objects.create(proyecto=pa, texto='Falta un tirador', muebles=[m])
    d = post(c, '/taller-a/puesto/api/instalacion', {'proyecto': pa.pk, 'mueble': m}).json()
    assert d['faltan'] == ['Bulto 1 de 2 sin entregar', 'Bulto 2 de 2 sin entregar', 'Tarea: Falta un tirador']
    assert [x['texto'] for x in d['tareas']] == ['Falta un tirador']
    r = post(c, '/taller-a/puesto/api/instalar', {'proyecto': pa.pk, 'mueble': m, 'motivo': ''})
    assert r.status_code == 400 and 'motivo' in r.json()['error']
    d = post(c, '/taller-a/puesto/api/instalar', {'proyecto': pa.pk, 'mueble': m, 'motivo': 'Se lo llevaron ellos'}).json()
    assert d['instalacion']['motivo'] == 'Se lo llevaron ellos' and len(d['instalacion']['faltantes']) == 3


def test_fotos_de_la_instalacion(cliente_de, t, pa):
    from tests.app.test_trabajos import imagen
    m = mueble_chico()
    c = cliente_de(t.armador_a)
    d = post(c, '/taller-a/puesto/api/instalar', {'proyecto': pa.pk, 'mueble': m, 'motivo': 'x'}).json()
    url = f'/taller-a/puesto/api/instalaciones/{d["instalacion"]["id"]}/fotos'
    assert c.post(url, b'no es una foto', content_type='image/jpeg').status_code == 415
    r = c.post(url, imagen(), content_type='image/jpeg')
    assert r.status_code == 200
    foto = r.json()['foto']
    assert c.get(f'/taller-a/puesto/api/fotos-de-instalacion/{foto}').status_code == 200
    # desde B no se ve ni se sube
    cb = cliente_de(t.dueno_b)
    assert cb.get(f'/taller-b/puesto/api/fotos-de-instalacion/{foto}').status_code == 404
    assert cb.post(url.replace('taller-a', 'taller-b'), imagen(), content_type='image/jpeg').status_code == 404


def test_rutas_de_entrega_de_a_no_andan_desde_b(cliente_de, t, pa):
    m = mueble_chico()
    cb = cliente_de(t.dueno_b)
    for ruta, d in [('armar', {'texto': '1', 'proyecto': pa.pk}), ('control', {'proyecto': pa.pk, 'mueble': m,
                                                                              'resultados': []}),
                    ('instalacion', {'proyecto': pa.pk, 'mueble': m}), ('instalar', {'proyecto': pa.pk, 'mueble': m}),
                    ('desinstalar', {'proyecto': pa.pk, 'mueble': m})]:
        assert post(cb, f'/taller-b/puesto/api/{ruta}', d).status_code == 404, ruta
    assert cb.get(f'/taller-b/visor/api/entrega?proyecto={pa.pk}').status_code == 404
