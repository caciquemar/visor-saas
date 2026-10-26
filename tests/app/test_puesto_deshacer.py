"""Mi puesto: deshacer lo escaneado por error (embalaje, control, instalación) y marcar un proceso desde la Lista sin
escanear (pedidos de Martín, 2026-10-26)."""
from datetime import timedelta

import pytest
from django.utils import timezone

from avance.models import Control, Etapa, FinDeMueble, Instalacion, Marca
from talleres.separacion import con_taller
from tests.app.ayudas import sumar
from tests.app.test_avance import etapas, mueble_chico, piezas_del, post, qr, sin_cache
from tests.app.test_etiquetas import etiqueta, proyecto_de
from trabajos.models import Trabajo
from usuarios.models import Usuario

sin_cache = sin_cache


@pytest.fixture
def pa(t):
    return proyecto_de(t.A)


def otro_armador(t):
    u = Usuario.objects.create_user(None, nombre='Pedro')
    sumar(u, t.A, 'armador', pin='2580')
    return u


def test_deshacer_el_embalaje_propio_y_reciente(cliente_de, t, pa):
    m = mueble_chico()
    pedro = otro_armador(t)
    c = cliente_de(t.armador_a)
    assert post(c, '/taller-a/puesto/api/embalar', {'texto': qr(etiqueta(t.A, pa, mueble=m))}).json()['resultado'] == 'ok'
    # otro armador no puede deshacer lo de Arturo
    r = post(cliente_de(pedro), '/taller-a/puesto/api/reabrir', {'proyecto': pa.pk, 'mueble': m})
    assert r.status_code == 403 and '15 minutos' in r.json()['error']
    # Arturo sí, recién
    c = cliente_de(t.armador_a)
    assert post(c, '/taller-a/puesto/api/reabrir', {'proyecto': pa.pk, 'mueble': m}).json()['resultado'] == 'ok'
    with con_taller(t.A):
        assert not FinDeMueble.objects.filter(anulado_en__isnull=True).exists()
    # pasados los 15 minutos, ya no
    post(c, '/taller-a/puesto/api/embalar', {'texto': qr(etiqueta(t.A, pa, mueble=m))})
    with con_taller(t.A):
        FinDeMueble.objects.update(cuando=timezone.now() - timedelta(minutes=16))
    assert post(c, '/taller-a/puesto/api/reabrir', {'proyecto': pa.pk, 'mueble': m}).status_code == 403
    assert post(cliente_de(t.oficina_a), '/taller-a/puesto/api/reabrir',
                {'proyecto': pa.pk, 'mueble': m}).json()['resultado'] == 'ok'


def test_borrar_el_control_y_sus_tareas_sin_empezar(cliente_de, t, pa):
    m = mueble_chico()
    c = cliente_de(t.armador_a)
    d = post(c, '/taller-a/puesto/api/control', {'texto': qr(etiqueta(t.A, pa, mueble=m))}).json()
    resultados = [{'punto': p['id'], 'ok': p['nombre'] != 'Frentes', 'nota': 'rayado'} for p in d['puntos']]
    d = post(c, '/taller-a/puesto/api/control', {'proyecto': pa.pk, 'mueble': m, 'resultados': resultados}).json()
    control = d['control']['id']
    assert len(d['tareas']) == 1
    assert post(cliente_de(otro_armador(t)), '/taller-a/puesto/api/control/borrar',
                {'control': control}).status_code == 403
    r = post(cliente_de(t.armador_a), '/taller-a/puesto/api/control/borrar', {'control': control})
    assert r.json()['resultado'] == 'ok'
    with con_taller(t.A):
        assert not Control.objects.exists() and not Trabajo.objects.exists()


def test_deshacer_la_instalacion_propia(cliente_de, t, pa):
    m = mueble_chico()
    c = cliente_de(t.armador_a)
    assert post(c, '/taller-a/puesto/api/instalar', {'texto': qr(etiqueta(t.A, pa, mueble=m))}).json()['resultado'] == 'ok'
    assert post(c, '/taller-a/puesto/api/desinstalar', {'proyecto': pa.pk, 'mueble': m}).json()['resultado'] == 'ok'
    with con_taller(t.A):
        assert not Instalacion.objects.filter(anulado_en__isnull=True).exists()


def test_marcar_desde_la_lista(cliente_de, t, pa):
    m = mueble_chico()
    armado = etapas(t.A)['Armado']
    c = cliente_de(t.armador_a)
    html = c.get(f'/taller-a/proyectos/{pa.pk}/entrega/?proceso={armado}').content.decode()
    assert '✓ Marcar armado' in html
    r = c.post(f'/taller-a/proyectos/{pa.pk}/entrega/', {'accion': 'marcar', 'mueble': m, 'proceso': armado})
    assert r.status_code == 302 and f'?proceso={armado}' in r['Location']
    with con_taller(t.A):
        assert Marca.objects.filter(etapa_id=armado, mueble=m, deshecha_en__isnull=True).count() == len(piezas_del(m))
    # embalaje (1 bulto), control (todo ok) e instalación, como al escanear
    with con_taller(t.A):
        ids = {e.tipo: e.pk for e in Etapa.objects.all()}
    for tipo in ('embalaje', 'control', 'instalacion'):
        c.post(f'/taller-a/proyectos/{pa.pk}/entrega/', {'accion': 'marcar', 'mueble': m, 'proceso': ids[tipo]})
    with con_taller(t.A):
        assert FinDeMueble.objects.get().bultos == 1 and Control.objects.get().ok
        assert Instalacion.objects.filter(anulado_en__isnull=True).count() == 1
    # la carga no: va por bulto
    html = c.get(f'/taller-a/proyectos/{pa.pk}/entrega/?proceso={ids["carga"]}').content.decode()
    assert '✓ Marcar' not in html
    r = c.post(f'/taller-a/proyectos/{pa.pk}/entrega/', {'accion': 'marcar', 'mueble': m, 'proceso': ids['carga']},
               follow=True)
    assert 'escaneando cada bulto' in r.content.decode()
    # desde B, nada
    cb = cliente_de(t.dueno_b)
    assert cb.post(f'/taller-b/proyectos/{pa.pk}/entrega/', {'accion': 'marcar', 'mueble': m,
                                                              'proceso': armado}).status_code == 404
