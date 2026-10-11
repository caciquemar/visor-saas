"""Ficha 13: avance por etapas, fin de fabricación, bultos y cargas.

Con el proyecto.json real de *cocina grondona* (como test_etiquetas.py), sin correr el conversor."""
import copy
import json

import pytest
from django.conf import settings

from avance import calculo
from avance.estado import estado_del_pedido
from avance.models import Bulto, Carga, Etapa, FinDeMueble, Marca, Movimiento, etapas_activas, etapas_del_taller
from etiquetas import claves, datos
from talleres.separacion import OtroTaller, con_taller
from tests.app.test_etiquetas import GRONDONA, etiqueta, guardar_version, proyecto_de, una_pieza


@pytest.fixture(autouse=True)
def sin_cache():
    datos._leer.cache_clear()
    yield
    datos._leer.cache_clear()


@pytest.fixture
def pa(t):
    return proyecto_de(t.A)


def etapas(taller):
    with con_taller(taller):
        return {e.nombre: e.pk for e in etapas_del_taller()}


def post(c, ruta, d):
    return c.post(ruta, json.dumps(d), content_type='application/json')


def marcar(c, texto, etapa, proyecto=None, slug='taller-a'):
    return post(c, f'/{slug}/puesto/api/marcar', {'texto': texto, 'etapa': etapa, 'proyecto': proyecto})


def qr(e, bulto=None):
    return f'{settings.URL_APP}/taller-a/e/{e.codigo}' + (f'/{bulto}' if bulto else '')


def mueble_chico():
    """Un mueble de grondona con pocas piezas (pero más de dos)."""
    return min(((n, c) for n, c in claves.muebles(GRONDONA).items() if c > 2), key=lambda kv: kv[1])[0]


def piezas_del(mueble):
    return [x for x in claves.piezas(GRONDONA) if x['panel']['mueble'] == mueble]


def marcar_todas(taller, proyecto, mueble, etapa_id, usuario=None):
    from django.utils import timezone
    from etiquetas.models import huella
    with con_taller(taller):
        etapa = Etapa.objects.get(pk=etapa_id)
        for x in piezas_del(mueble):
            Marca.objects.create(proyecto=proyecto, etapa=etapa, clave=x['clave'], huella=huella(x['clave']),
                                 mueble=mueble, por=usuario, cuando=timezone.now())


# ---------------------------------------------------------------- etapas

def test_etapas_por_defecto_por_taller(t):
    assert list(etapas(t.A)) == ['Cortada', 'Canteada', 'Mecanizada', 'Armada']
    assert set(etapas(t.A).values()).isdisjoint(etapas(t.B).values())


def test_solo_el_dueno_cambia_las_etapas(cliente_de, t):
    e = etapas(t.A)
    assert cliente_de(t.armador_a).get('/taller-a/etapas/').status_code == 403
    c = cliente_de(t.dueno_a)
    assert c.get('/taller-a/etapas/').status_code == 200
    datos_ = {'accion': 'guardar', **{f'nombre-{i}': n for n, i in e.items()},
              **{f'activa-{i}': '1' for n, i in e.items() if n != 'Mecanizada'}, f'nombre-{e["Cortada"]}': 'Corte'}
    c.post('/taller-a/etapas/', datos_)
    with con_taller(t.A):
        assert [x.nombre for x in etapas_activas()] == ['Corte', 'Canteada', 'Armada']


# ---------------------------------------------------------------- marcar piezas

def test_marcar_por_qr_y_avisar_la_repetida(cliente_de, t, pa):
    x = una_pieza(lambda x: x['panel']['num'])
    e = etiqueta(t.A, pa, x)
    corte = etapas(t.A)['Cortada']
    c = cliente_de(t.armador_a)
    d = marcar(c, qr(e), corte, pa.pk).json()
    assert d['resultado'] == 'ok' and not d['otro_proyecto'] and d['pieza']['num'] == x['panel']['num']
    assert d['mueble'] == {'hechas': 1, 'piezas': claves.muebles(GRONDONA)[x['panel']['mueble']]}
    # la misma etiqueta otra vez (o escrita a mano): avisa quién y cuándo, no cambia nada
    d = marcar(c, e.codigo.lower(), corte).json()
    assert d['resultado'] == 'ya' and d['ya']['por'] == 'Arturo' and d['ya']['cuando']
    with con_taller(t.A):
        m = Marca.objects.get()
        assert m.por == t.armador_a and m.cuando and m.mueble == x['panel']['mueble']


def test_numero_de_mecanizado_va_a_la_siguiente_copia(cliente_de, t, pa):
    x = una_pieza(lambda x: x['de'] == 2 and x['panel']['num'])
    corte = etapas(t.A)['Cortada']
    c = cliente_de(t.armador_a)
    numero = 'M-' + x['panel']['num']          # como lo lee el código de barras de OptiCut
    copias = [marcar(c, numero, corte, pa.pk).json() for _ in range(3)]
    assert [d['resultado'] for d in copias] == ['ok', 'ok', 'ya']
    assert {d['pieza']['copia'] for d in copias[:2]} == {1, 2}
    # sin proyecto elegido no se sabe de cuál es
    assert marcar(c, numero, corte).json()['resultado'] == 'error'
    assert 'no está' in marcar(c, '999999', corte, pa.pk).json()['error']


def test_pieza_de_otro_proyecto_se_marca_en_el_suyo(cliente_de, t, pa):
    otro = proyecto_de(t.A, nombre='otra cocina')
    e = etiqueta(t.A, pa, una_pieza())
    d = marcar(cliente_de(t.armador_a), qr(e), etapas(t.A)['Canteada'], otro.pk).json()
    assert d['resultado'] == 'ok' and d['otro_proyecto'] and d['proyecto']['id'] == pa.pk
    with con_taller(t.A):
        assert Marca.objects.get().proyecto == pa


def test_lecturas_que_no_marcan(cliente_de, t, pa):
    c = cliente_de(t.armador_a)
    corte = etapas(t.A)['Cortada']
    mueble = etiqueta(t.A, pa, mueble=mueble_chico())
    assert 'mueble' in marcar(c, qr(mueble, 1), corte).json()['error']
    assert 'otro taller' in marcar(c, f'{settings.URL_APP}/taller-b/e/ABCDEFGH', corte).json()['error']
    assert marcar(c, 'ABCDEFGH', corte).json()['resultado'] == 'error'
    assert marcar(c, 'x', 999999).status_code == 400            # etapa que no existe


def test_deshacer_y_volver_a_marcar(cliente_de, t, pa):
    e = etiqueta(t.A, pa, una_pieza())
    corte = etapas(t.A)['Cortada']
    c = cliente_de(t.armador_a)
    d = marcar(c, e.codigo, corte).json()
    assert post(c, '/taller-a/puesto/api/deshacer', {'marca': d['marca']}).json()['resultado'] == 'ok'
    assert post(c, '/taller-a/puesto/api/deshacer', {'marca': d['marca']}).status_code == 404
    assert marcar(c, e.codigo, corte).json()['resultado'] == 'ok'
    with con_taller(t.A):
        vieja, nueva = Marca.objects.order_by('pk')
        assert vieja.deshecha_por == t.armador_a and vieja.deshecha_en and nueva.deshecha_en is None


# ---------------------------------------------------------------- porcentaje

def test_porcentaje_es_el_promedio_de_etapas(t, pa):
    m = mueble_chico()
    e = etapas(t.A)
    marcar_todas(t.A, pa, m, e['Cortada'])
    marcar_todas(t.A, pa, m, e['Canteada'])
    with con_taller(t.A):
        a = calculo.avance(pa)
        assert a['muebles'][m]['pct'] == 50
        assert a['total']['hechos'] == 2 * len(piezas_del(m))
        Etapa.objects.filter(pk=e['Mecanizada']).update(activa=False)
        assert calculo.avance(pa)['muebles'][m]['pct'] == 66          # 2 de 3, para abajo
        marcar_todas(t.A, pa, m, e['Armada'])
        assert calculo.avance(pa)['muebles'][m]['pct'] == 100


def test_version_nueva_conserva_el_avance_y_avisa_las_piezas_nuevas(t, pa):
    m = mueble_chico()
    marcar_todas(t.A, pa, m, etapas(t.A)['Cortada'])
    nueva = copy.deepcopy(GRONDONA)
    extra = copy.deepcopy(next(p for p in nueva['paneles'] if p.get('pieza')))
    extra.update(id='extra-1', nombre='Estante agregado', num='9999')
    nueva['paneles'].append(extra)
    guardar_version(t.A, pa, nueva, 2)
    with con_taller(t.A):
        assert calculo.avance(pa)['muebles'][m]['por_etapa'][etapas(t.A)['Cortada']] == len(piezas_del(m))
        assert [x['panel']['nombre'] for x in calculo.piezas_nuevas(pa)] == ['Estante agregado']
    # una versión sin una de las piezas marcadas: esa marca deja de contar
    sacada = piezas_del(m)[0]['panel']['id']
    guardar_version(t.A, pa, {**GRONDONA, 'paneles': [p for p in GRONDONA['paneles'] if p['id'] != sacada]}, 3)
    with con_taller(t.A):
        a = calculo.avance(pa)
        assert a['sueltas'] == 1 and a['muebles'][m]['por_etapa'][etapas(t.A)['Cortada']] == len(piezas_del(m)) - 1


# ---------------------------------------------------------------- fin de fabricación

def terminar(c, proyecto, mueble, bultos=1, motivo=''):
    return post(c, '/taller-a/puesto/api/terminar',
                {'proyecto': proyecto.pk, 'mueble': mueble, 'bultos': bultos, 'motivo': motivo})


def test_fin_de_fabricacion_con_faltantes_pide_motivo(cliente_de, t, pa):
    m = mueble_chico()
    c = cliente_de(t.armador_a)
    e = etiqueta(t.A, pa, mueble=m)
    d = post(c, '/taller-a/puesto/api/mueble', {'texto': qr(e, 1)}).json()
    assert d['mueble'] == m and d['etapa'] == 'Armada' and len(d['faltan']) == len(piezas_del(m)) and d['fin'] is None
    r = terminar(c, pa, m, 2)
    assert r.status_code == 400 and 'motivo' in r.json()['error']
    d = terminar(c, pa, m, 2, 'el frente va después').json()
    assert d['fin']['bultos'] == 2 and d['fin']['por'] == 'Arturo' and len(d['fin']['faltantes']) == len(piezas_del(m))
    assert [b['estado'] for b in d['fin']['lista']] == ['embalado', 'embalado']
    assert terminar(c, pa, m, 1, 'otra vez').status_code == 409
    with con_taller(t.A):
        assert Movimiento.objects.filter(a='embalado', usuario=t.armador_a).count() == 2


def test_fin_sin_faltantes_y_reabrir(cliente_de, t, pa):
    m = mueble_chico()
    marcar_todas(t.A, pa, m, etapas(t.A)['Armada'])
    assert terminar(cliente_de(t.armador_a), pa, m).json()['fin']['motivo'] == ''
    reabrir = {'proyecto': pa.pk, 'mueble': m}
    assert post(cliente_de(t.armador_a), '/taller-a/puesto/api/reabrir', reabrir).status_code == 403
    assert post(cliente_de(t.oficina_a), '/taller-a/puesto/api/reabrir', reabrir).status_code == 200
    with con_taller(t.A):
        f = FinDeMueble.objects.get()
        assert f.anulado_por == t.oficina_a and f.anulado_en


# ---------------------------------------------------------------- cargas

def test_carga_con_un_bulto_de_menos(cliente_de, t, pa):
    m = mueble_chico()
    otro = next(n for n in claves.muebles(GRONDONA) if n != m)
    c = cliente_de(t.armador_a)
    terminar(c, pa, m, 2, 'prueba')
    r = c.post(f'/taller-a/proyectos/{pa.pk}/cargas/nueva/', {'todo': '0', 'mueble': [m, otro]})
    with con_taller(t.A):
        carga = Carga.objects.get()
    assert r['Location'] == f'/taller-a/cargas/{carga.pk}/'
    e = etiqueta(t.A, pa, mueble=m)
    bulto = f'/taller-a/puesto/api/cargas/{carga.pk}/bulto'
    d = post(c, bulto, {'texto': qr(e, 1)}).json()
    assert d['resultado'] == 'ok' and d['carga']['cargados'] == 1
    assert d['carga']['faltantes'] == [f'{m} · bulto 2 de 2', f'{otro} · sin terminar']
    assert post(c, bulto, {'texto': qr(e, 1)}).json()['resultado'] == 'ya'
    assert 'impresión vieja' in post(c, bulto, {'texto': qr(e, 3)}).json()['error']
    assert 'pieza' in post(c, bulto, {'texto': etiqueta(t.A, pa, una_pieza()).codigo}).json()['error']
    # no sale con faltantes sin un motivo
    pagina = c.get(f'/taller-a/cargas/{carga.pk}/').content.decode()
    assert 'Faltan 2' in pagina and f'{m} · bulto 2 de 2' in pagina
    r = c.post(f'/taller-a/cargas/{carga.pk}/', {'motivo': ''})
    assert r.status_code == 400 and 'motivo' in r.content.decode()
    c.post(f'/taller-a/cargas/{carga.pk}/', {'motivo': 'el bulto 2 va mañana'})
    with con_taller(t.A):
        carga.refresh_from_db()
        assert carga.estado == 'salio' and carga.salio_por == t.armador_a and carga.salio_en
        assert carga.faltantes == [f'{m} · bulto 2 de 2', f'{otro} · sin terminar']
        b = Bulto.objects.get(numero=1)
        assert b.estado == 'cargado' and b.cargado_por == t.armador_a and b.carga == carga
    # una vez que salió no se le suman bultos; en obra se entrega
    assert post(c, bulto, {'texto': qr(e, 2)}).json()['resultado'] == 'error'
    d = post(c, bulto, {'texto': qr(e, 1), 'entregar': True}).json()
    assert d['resultado'] == 'ok' and d['carga']['estado'] == 'entregada'
    with con_taller(t.A):
        assert [(x.de, x.a) for x in Movimiento.objects.filter(bulto__numero=1)] == [
            ('', 'embalado'), ('embalado', 'cargado'), ('cargado', 'entregado')]
        assert estado_del_pedido(pa)['estado'] == 'en_fabricacion'


def test_carga_vacia_no_sale_y_deshacer_un_bulto(cliente_de, t, pa):
    m = mueble_chico()
    c = cliente_de(t.armador_a)
    terminar(c, pa, m, 1, 'prueba')
    c.post(f'/taller-a/proyectos/{pa.pk}/cargas/nueva/', {'todo': '1'})
    with con_taller(t.A):
        carga = Carga.objects.get()
        assert carga.muebles == []
    assert 'vacía' in c.post(f'/taller-a/cargas/{carga.pk}/', {'motivo': 'x'}).content.decode()
    d = post(c, f'/taller-a/puesto/api/cargas/{carga.pk}/bulto', {'texto': qr(etiqueta(t.A, pa, mueble=m), 1)}).json()
    d = post(c, f'/taller-a/puesto/api/cargas/{carga.pk}/deshacer', {'bulto': d['bulto']}).json()
    assert d['carga']['cargados'] == 0
    with con_taller(t.A):
        assert Bulto.objects.get().estado == 'embalado'


# ---------------------------------------------------------------- pantallas

def test_pantallas(cliente_de, t, pa):
    m = mueble_chico()
    marcar_todas(t.A, pa, m, etapas(t.A)['Cortada'], t.armador_a)
    c = cliente_de(t.armador_a)
    assert 'Cortada' in c.get('/taller-a/puesto/').content.decode()
    assert '25%' in c.get(f'/taller-a/proyectos/{pa.pk}/').content.decode()
    assert '%' in c.get('/taller-a/proyectos/').content.decode()
    d = c.get(f'/taller-a/visor/api/avance?proyecto={pa.pk}').json()
    assert d['muebles'][m]['pct'] == 25 and d['final'] == etapas(t.A)['Armada'] and d['nuevas'] == []
    assert d['paneles'][piezas_del(m)[0]['panel']['id']] == [etapas(t.A)['Cortada']]


# ---------------------------------------------------------------- separación entre talleres

def test_avance_de_a_no_se_ve_ni_se_toca_desde_b(cliente_de, t, pa):
    m = mueble_chico()
    ca = cliente_de(t.armador_a)
    e = etiqueta(t.A, pa, una_pieza())
    marca = marcar(ca, e.codigo, etapas(t.A)['Cortada']).json()['marca']
    terminar(ca, pa, m, 1, 'prueba')
    ca.post(f'/taller-a/proyectos/{pa.pk}/cargas/nueva/', {'todo': '1'})
    with con_taller(t.A):
        carga = Carga.objects.get()
        fin, bulto = FinDeMueble.objects.get(), Bulto.objects.get()
    etapas_a = list(etapas(t.A).values())
    cb = cliente_de(t.dueno_b)
    corte_b = etapas(t.B)['Cortada']
    # por la API de B, nada de A existe
    assert 'no es de este taller' in marcar(cb, e.codigo, corte_b, slug='taller-b').json()['error']
    assert marcar(cb, e.codigo, etapas(t.A)['Cortada'], slug='taller-b').status_code == 400     # etapa de A
    assert marcar(cb, '1', corte_b, pa.pk, slug='taller-b').status_code == 404                   # proyecto de A
    assert post(cb, '/taller-b/puesto/api/deshacer', {'marca': marca}).status_code == 404
    assert post(cb, '/taller-b/puesto/api/terminar',
                {'proyecto': pa.pk, 'mueble': m, 'bultos': 1, 'motivo': 'x'}).status_code == 404
    assert post(cb, '/taller-b/puesto/api/reabrir', {'proyecto': pa.pk, 'mueble': m}).status_code == 404
    assert cb.get(f'/taller-b/puesto/api/mueble?proyecto={pa.pk}&mueble={m}').status_code == 404
    assert cb.get(f'/taller-b/puesto/api/cargas/{carga.pk}').status_code == 404
    assert post(cb, f'/taller-b/puesto/api/cargas/{carga.pk}/bulto', {'texto': 'x'}).status_code == 404
    assert post(cb, f'/taller-b/puesto/api/cargas/{carga.pk}/deshacer', {'bulto': bulto.pk}).status_code == 404
    assert cb.get(f'/taller-b/cargas/{carga.pk}/').status_code == 404
    assert cb.post(f'/taller-b/proyectos/{pa.pk}/cargas/nueva/', {'todo': '1'}).status_code == 404
    assert cb.get(f'/taller-b/visor/api/avance?proyecto={pa.pk}').status_code == 404
    # y por las direcciones de A, B no entra
    assert cb.get('/taller-a/puesto/').status_code == 404
    assert cb.get(f'/taller-a/cargas/{carga.pk}/').status_code == 404
    # desde B, los datos de A ni se ven ni se escriben
    with con_taller(t.B):
        for modelo in (Marca, FinDeMueble, Bulto, Carga, Movimiento):
            assert not modelo.objects.exists(), modelo
        assert not Etapa.objects.filter(pk__in=etapas_a).exists()         # B tiene las suyas
        with pytest.raises(OtroTaller):
            Carga.objects.create(proyecto=pa, creada_en=fin.cuando)
        with pytest.raises(OtroTaller):
            Bulto.objects.create(fin=fin, proyecto=pa, mueble=m, numero=2, embalado_en=fin.cuando)
        with pytest.raises(OtroTaller):
            Marca.objects.create(proyecto=pa, etapa=Etapa.objects.create(nombre='x'), clave={}, huella='h',
                                 cuando=fin.cuando)
    with con_taller(t.A):
        assert Marca.objects.count() == 1 and Bulto.objects.count() == 1 and Carga.objects.count() == 1


def test_ordenar_las_etapas_arrastrando(cliente_de, t):
    e = etapas(t.A)
    nuevo = [e['Canteada'], e['Cortada'], e['Armada'], e['Mecanizada']]
    datos_ = {'accion': 'guardar', 'orden': ','.join(map(str, nuevo)), **{f'nombre-{i}': n for n, i in e.items()},
              **{f'activa-{i}': '1' for i in e.values()}}
    c = cliente_de(t.dueno_a)
    c.post('/taller-a/etapas/', datos_)
    with con_taller(t.A):
        assert [x.pk for x in etapas_activas()] == nuevo
        assert etapas_activas()[-1].nombre == 'Mecanizada'        # la última es la que mira "Fabricación terminada"
    pagina = c.get('/taller-a/etapas/').content.decode()            # y la pantalla las muestra en ese orden
    assert [pagina.index(f'name="nombre-{i}"') for i in nuevo] == sorted(pagina.index(f'name="nombre-{i}"') for i in nuevo)
