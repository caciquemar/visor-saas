"""Ficha 21: ABM de cargas desde el proyecto, carga nueva al escanear y cerrar con faltantes (quedan para otro envío).

Con el proyecto.json real de *cocina grondona*, como test_avance.py."""
import pytest

from avance.acciones import pendientes_de_envio
from avance.models import Bulto, Carga
from talleres.separacion import con_taller
from tests.app.test_avance import mueble_chico, post, qr, sin_cache, terminar
from tests.app.test_etiquetas import GRONDONA, etiqueta, proyecto_de

sin_cache = sin_cache


@pytest.fixture
def pa(t):
    return proyecto_de(t.A)


def dos_muebles():
    from etiquetas import claves
    m = mueble_chico()
    otro = next(n for n in claves.muebles(GRONDONA) if n != m)
    return m, otro


def la_carga(t):
    with con_taller(t.A):
        return Carga.objects.order_by('pk').last()


def test_alta_trae_tildado_lo_pendiente_y_filtra_por_proceso(cliente_de, t, pa):
    m, otro = dos_muebles()
    c = cliente_de(t.armador_a)
    terminar(c, pa, m, 1, 'x')
    html = c.get(f'/taller-a/proyectos/{pa.pk}/').content.decode()
    assert 'Solo los que completaron' in html and 'Los que faltan enviar' in html
    # el embalado lleva el id de Embalaje en data-procesos (para el filtro)
    with con_taller(t.A):
        from avance.models import Etapa
        embalaje = Etapa.objects.get(tipo='embalaje').pk
    fila = html[html.index(f'value="{m}"') - 200:html.index(f'value="{m}"')]
    assert f' {embalaje} ' in fila
    c.post(f'/taller-a/proyectos/{pa.pk}/cargas/nueva/', {'mueble': [m]})
    carga = la_carga(t)
    assert carga.muebles == [m] and not carga.libre
    assert post(c, '/taller-a/proyectos/0/cargas/nueva/', {}).status_code in (404, 405)


def test_modificar_y_no_sacar_un_mueble_con_bultos(cliente_de, t, pa):
    m, otro = dos_muebles()
    c = cliente_de(t.armador_a)
    terminar(c, pa, m, 1, 'x')
    c.post(f'/taller-a/proyectos/{pa.pk}/cargas/nueva/', {'mueble': [m]})
    carga = la_carga(t)
    c.post(f'/taller-a/cargas/{carga.pk}/modificar/', {'mueble': [m, otro]})
    assert set(la_carga(t).muebles) == {m, otro}
    post(c, f'/taller-a/puesto/api/cargas/{carga.pk}/bulto', {'texto': qr(etiqueta(t.A, pa, mueble=m), 1)})
    r = c.post(f'/taller-a/cargas/{carga.pk}/modificar/', {'mueble': [otro]}, follow=True)
    assert 'ya tiene bultos' in r.content.decode() and m in la_carga(t).muebles
    assert 'Modificar la carga' in c.get(f'/taller-a/cargas/{carga.pk}/modificar/').content.decode()


def test_anular_devuelve_los_bultos(cliente_de, t, pa):
    m, _ = dos_muebles()
    c = cliente_de(t.armador_a)
    terminar(c, pa, m, 1, 'x')
    c.post(f'/taller-a/proyectos/{pa.pk}/cargas/nueva/', {'mueble': [m]})
    carga = la_carga(t)
    post(c, f'/taller-a/puesto/api/cargas/{carga.pk}/bulto', {'texto': qr(etiqueta(t.A, pa, mueble=m), 1)})
    assert c.post(f'/taller-a/cargas/{carga.pk}/anular/').status_code == 403          # el armador no anula
    o = cliente_de(t.oficina_a)
    o.post(f'/taller-a/cargas/{carga.pk}/anular/')
    with con_taller(t.A):
        carga.refresh_from_db()
        b = Bulto.objects.get()
        assert carga.estado == 'anulada' and carga.anulada_por == t.oficina_a
        assert b.estado == 'embalado' and b.carga is None
        assert m in pendientes_de_envio(pa)
    assert f'carga {carga.pk}"' not in o.get('/taller-a/puesto/').content.decode()    # ya no se elige en el puesto
    assert post(o, f'/taller-a/puesto/api/cargas/{carga.pk}/bulto',
                {'texto': qr(etiqueta(t.A, pa, mueble=m), 1)}).json()['resultado'] == 'error'


def test_lo_que_falta_queda_para_otro_envio(cliente_de, t, pa):
    m, otro = dos_muebles()
    c = cliente_de(t.armador_a)
    terminar(c, pa, m, 2, 'x')
    terminar(c, pa, otro, 1, 'x')
    c.post(f'/taller-a/proyectos/{pa.pk}/cargas/nueva/', {'mueble': [m, otro]})
    primera = la_carga(t)
    post(c, f'/taller-a/puesto/api/cargas/{primera.pk}/bulto', {'texto': qr(etiqueta(t.A, pa, mueble=m), 1)})
    post(c, f'/taller-a/puesto/api/cargas/{primera.pk}/bulto', {'texto': qr(etiqueta(t.A, pa, mueble=otro), 1)})
    c.post(f'/taller-a/cargas/{primera.pk}/', {'motivo': ''})                         # sale con el bulto 2 de m
    with con_taller(t.A):
        assert m in pendientes_de_envio(pa) and otro not in pendientes_de_envio(pa)
    # la segunda carga: lo que ya salió no es faltante
    c.post(f'/taller-a/proyectos/{pa.pk}/cargas/nueva/', {'mueble': [m, otro]})
    segunda = la_carga(t)
    d = c.get(f'/taller-a/puesto/api/cargas/{segunda.pk}').json()
    assert d['faltantes'] == [f'{m} · bulto 2 de 2'] and d['total'] == 1
