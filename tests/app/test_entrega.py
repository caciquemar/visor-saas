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
    marcar_todas(t.A, pa, m, etapas(t.A)['Armado'])
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
    marcar(c, etiqueta(t.A, pa, piezas[0]).codigo, etapas(t.A)['Armado'])       # una ya estaba armada
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
    marcar_todas(t.A, pa, m, etapas(t.A)['Armado'])
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

def cargar_y_salir(c, t, pa, m, bultos=1):
    """Embalado en `bultos`, cargado entero y salido a obra (ya no hay "Entregar en obra": se entrega al instalar)."""
    terminar(c, pa, m, bultos, 'prueba')
    c.post(f'/taller-a/proyectos/{pa.pk}/cargas/nueva/', {'todo': '0', 'mueble': [m]})
    with con_taller(t.A):
        carga = Carga.objects.last()
    e = etiqueta(t.A, pa, mueble=m)
    for n in range(1, bultos + 1):
        post(c, f'/taller-a/puesto/api/cargas/{carga.pk}/bulto', {'texto': qr(e, n)})
    c.post(f'/taller-a/cargas/{carga.pk}/', {'motivo': ''})
    return carga


def test_instalar_al_escanear_entrega_los_bultos_y_deshacer_solo_gestion(cliente_de, t, pa):
    m = mueble_chico()
    c = cliente_de(t.armador_a)
    carga = cargar_y_salir(c, t, pa, m)
    assert paso(t.A, pa, m)['paso'] == 'cargado'           # con instalación prendida no hay "entregado"
    d = post(c, '/taller-a/puesto/api/instalar', {'texto': qr(etiqueta(t.A, pa, mueble=m), 1)}).json()
    assert d['resultado'] == 'ok' and d['instalacion']['por'] == 'Arturo'
    assert d['bultos'] == {'total': 1, 'cargados': 1, 'entregados': 1}
    with con_taller(t.A):
        carga.refresh_from_db()
        assert carga.estado == 'entregada'
    assert paso(t.A, pa, m)['paso'] == 'instalado'
    # otra vez: ya estaba, no se duplica
    d = post(c, '/taller-a/puesto/api/instalar', {'texto': qr(etiqueta(t.A, pa, mueble=m))}).json()
    assert d['resultado'] == 'ya'
    with con_taller(t.A):
        assert Instalacion.objects.filter(anulado_en__isnull=True).count() == 1
    assert post(c, '/taller-a/puesto/api/desinstalar', {'proyecto': pa.pk, 'mueble': m}).status_code == 403
    assert post(cliente_de(t.oficina_a), '/taller-a/puesto/api/desinstalar',
                {'proyecto': pa.pk, 'mueble': m}).json()['resultado'] == 'ok'
    assert paso(t.A, pa, m)['paso'] == 'cargado'


def test_instalar_sin_embalar_registra_igual(cliente_de, t, pa):
    """Sin correlatividad: instalar un mueble que no pasó por nada lo registra."""
    from trabajos.models import Trabajo
    m = mueble_chico()
    c = cliente_de(t.armador_a)
    with con_taller(t.A):
        Trabajo.objects.create(proyecto=pa, texto='Falta un tirador', muebles=[m])
    d = post(c, '/taller-a/puesto/api/instalar', {'texto': qr(etiqueta(t.A, pa, mueble=m))}).json()
    assert d['resultado'] == 'ok' and [x['texto'] for x in d['tareas']] == ['Falta un tirador']
    assert paso(t.A, pa, m)['paso'] == 'instalado'


def test_fotos_de_la_instalacion(cliente_de, t, pa):
    from tests.app.test_trabajos import imagen
    m = mueble_chico()
    c = cliente_de(t.armador_a)
    d = post(c, '/taller-a/puesto/api/instalar', {'texto': qr(etiqueta(t.A, pa, mueble=m))}).json()
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
                    ('embalar', {'texto': '1', 'proyecto': pa.pk}), ('bultos', {'proyecto': pa.pk, 'mueble': m,
                                                                               'bultos': 2}),
                    ('instalacion', {'proyecto': pa.pk, 'mueble': m}), ('instalar', {'texto': '1', 'proyecto': pa.pk}),
                    ('desinstalar', {'proyecto': pa.pk, 'mueble': m})]:
        assert post(cb, f'/taller-b/puesto/api/{ruta}', d).status_code == 404, ruta
    assert cb.get(f'/taller-b/visor/api/entrega?proyecto={pa.pk}').status_code == 404


# ---------------------------------------------------------------- Lista de entrega y pantalla del proyecto

def test_lista_de_entrega(cliente_de, t, pa):
    m = mueble_chico()
    c = cliente_de(t.armador_a)
    cargar_y_salir(c, t, pa, m)
    r = c.get(f'/taller-a/proyectos/{pa.pk}/entrega/')
    assert r.status_code == 200
    html = r.content.decode()
    assert m in html and 'Cargado' in html and 'Marcar instalado' not in html          # el armador no marca acá
    fila, = [x for x in r.context['muebles'] if x['nombre'] == m]
    assert fila['paso'] == 'cargado' and fila['paso_nombre'] == 'Cargado'
    assert 'Cargado' in c.get(f'/taller-a/proyectos/{pa.pk}/entrega/?filas=1').content.decode()
    assert c.post(f'/taller-a/proyectos/{pa.pk}/entrega/', {'mueble': m, 'accion': 'instalar'}).status_code == 403
    # la oficina marca instalado desde la Lista, y lo deshace
    o = cliente_de(t.oficina_a)
    assert 'Marcar instalado' in o.get(f'/taller-a/proyectos/{pa.pk}/entrega/').content.decode()
    o.post(f'/taller-a/proyectos/{pa.pk}/entrega/', {'mueble': m, 'accion': 'instalar', 'nota': 'Ok'})
    assert paso(t.A, pa, m)['paso'] == 'instalado'
    o.post(f'/taller-a/proyectos/{pa.pk}/entrega/', {'mueble': m, 'accion': 'desinstalar'})
    assert paso(t.A, pa, m)['paso'] == 'cargado'
    # sin correlatividad: un mueble que no pasó por nada se marca igual
    otro = next(x for x in sorted(set(p['panel']['mueble'] for p in piezas_del_proyecto())) if x != m)
    o.post(f'/taller-a/proyectos/{pa.pk}/entrega/', {'mueble': otro, 'accion': 'instalar'})
    assert paso(t.A, pa, otro)['paso'] == 'instalado'
    # la pantalla del proyecto lleva a la Lista y al 3D
    html = o.get(f'/taller-a/proyectos/{pa.pk}/').content.decode()
    assert f'/taller-a/proyectos/{pa.pk}/entrega/' in html
    # desde B, nada
    assert cliente_de(t.dueno_b).get(f'/taller-b/proyectos/{pa.pk}/entrega/').status_code == 404


def piezas_del_proyecto():
    from etiquetas import claves
    from tests.app.test_etiquetas import GRONDONA
    return claves.piezas(GRONDONA)


def test_visor_api_entrega(cliente_de, t, pa):
    m = mueble_chico()
    c = cliente_de(t.armador_a)
    marcar_todas(t.A, pa, m, etapas(t.A)['Armado'])
    d = c.get(f'/taller-a/visor/api/entrega?proyecto={pa.pk}').json()
    assert [p['clave'] for p in d['pasos']] == ['sin_armar', 'armado', 'controlado', 'embalado', 'cargado', 'instalado']
    assert d['muebles'][m]['paso'] == 'armado' and d['totales']['armado'] == 1
    assert sum(d['totales'].values()) == len(d['muebles'])


# ---------------------------------------------------------------- tablero y estado del pedido

def test_tablero_y_estado_del_pedido_con_la_entrega(cliente_de, t, pa):
    from avance.estado import estado_del_pedido
    m = mueble_chico()
    c = cliente_de(t.armador_a)
    cargar_y_salir(c, t, pa, m)
    post(c, '/taller-a/puesto/api/instalar', {'texto': qr(etiqueta(t.A, pa, mueble=m))})
    ctx = c.get('/taller-a/tablero/').context
    total = len(ctx['proyectos'][0]['entrega']) and ctx['proyectos'][0]['muebles']
    assert ctx['proyectos'][0]['instalados'] == 1 and ctx['por_instalar'] == total - 1
    assert {p['clave']: p['n'] for p in ctx['entrega']}['instalado'] == 1
    with con_taller(t.A):
        e = estado_del_pedido(pa)
    assert e['estado'] != 'instalado' and [x['instalado'] for x in e['muebles'] if x['nombre'] == m] == [True]
    # con todos los muebles instalados, el pedido queda instalado y el proyecto sale de "en curso"
    with con_taller(t.A):
        for n in pasos_.pasos(pa)['muebles']:
            if n != m:
                Instalacion.objects.create(proyecto=pa, mueble=n, cuando=timezone.now())
        assert estado_del_pedido(pa)['estado'] == 'instalado'
    ctx = c.get('/taller-a/tablero/').context
    assert ctx['en_curso'] == 0 or all(x['proyecto'] != pa for x in ctx['proyectos'])


def test_control_despues_de_embalar_se_ve_en_el_tablero(cliente_de, t, pa):
    """Pedido de Martín: un mueble ya embalado (o cargado) que se controla sigue en su paso, pero el tablero cuenta el
    control aparte."""
    m = mueble_chico()
    c = cliente_de(t.armador_a)
    terminar(c, pa, m, 1, 'prueba')
    ids = {p['nombre']: p['id'] for p in post(c, '/taller-a/puesto/api/control',
                                               {'texto': qr(etiqueta(t.A, pa, mueble=m))}).json()['puntos']}
    post(c, '/taller-a/puesto/api/control', {'proyecto': pa.pk, 'mueble': m,
                                             'resultados': [{'punto': i, 'ok': n != 'Herrajes'} for n, i in ids.items()]})
    assert paso(t.A, pa, m)['paso'] == 'embalado'
    r = c.get('/taller-a/tablero/')
    assert r.context['controles']['obs'] == 1 and r.context['proyectos'][0]['controles']['obs'] == 1
    assert '1 con observaciones' in r.content.decode()
