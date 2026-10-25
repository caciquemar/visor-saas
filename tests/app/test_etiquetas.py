"""Ficha 12: etiquetas con QR por pieza y por mueble.

Los proyectos se arman con el proyecto.json real de *cocina grondona* (muestras/), sin correr el conversor."""
import copy
import gzip
import json
import re

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from etiquetas import claves, datos, pdf
from etiquetas.models import ALFABETO, Etiqueta, FormatoEtiquetas
from proyectos.models import Proyecto, Version
from talleres.separacion import OtroTaller, con_taller
from tests.app.ayudas import MUESTRAS

GRONDONA = json.load(gzip.open(MUESTRAS / 'cocina grondona' / 'esperado' / 'proyecto.json.gz', 'rt',
                               encoding='utf-8'))


@pytest.fixture(autouse=True)
def sin_cache():
    datos._leer.cache_clear()
    yield
    datos._leer.cache_clear()


def guardar_version(taller, proyecto, contenido, numero):
    with con_taller(taller):
        v = Version.objects.create(proyecto=proyecto, numero=numero, estado=Version.Estado.LISTO)
        ruta = f'{v.carpeta()}resultado/proyecto.json'
        default_storage.save(ruta, ContentFile(json.dumps(contenido).encode()))
        v.archivo_proyecto = ruta
        v.save()
        proyecto.version_actual = v
        proyecto.save()
    return v


def proyecto_de(taller, contenido=None, nombre='cocina grondona'):
    with con_taller(taller):
        p = Proyecto.objects.create(nombre=nombre, cliente='Grondona', direccion='Calle 123', en_produccion=True)
    guardar_version(taller, p, contenido or GRONDONA, 1)
    return p


@pytest.fixture
def pa(t):
    return proyecto_de(t.A)


def una_pieza(cond=lambda x: True):
    return next(x for x in claves.piezas(GRONDONA) if cond(x))


def etiqueta(taller, proyecto, x=None, mueble=None):
    with con_taller(taller):
        if mueble:
            return Etiqueta.para(proyecto, 'mueble', {'mueble': mueble})
        return Etiqueta.para(proyecto, 'pieza', x['clave'])


# ---------------------------------------------------------------- qué es una pieza (sin base)

def test_solo_llevan_etiqueta_las_piezas_de_la_lista():
    piezas = claves.piezas(GRONDONA)
    assert len(piezas) == sum(1 for p in GRONDONA['paneles'] if p.get('pieza'))
    assert any(not x['panel']['num'] for x in piezas)          # también las que no tienen número de mecanizado
    assert all(x['panel']['pieza'] for x in piezas)


@pytest.mark.parametrize('carpeta', sorted(p.parent.parent.name for p in MUESTRAS.glob('*/esperado/proyecto.json.gz')))
def test_cada_pieza_tiene_su_clave_en_todas_las_muestras(carpeta):
    d = json.load(gzip.open(MUESTRAS / carpeta / 'esperado' / 'proyecto.json.gz', 'rt', encoding='utf-8'))
    piezas = claves.piezas(d)
    vistas = [json.dumps(x['clave'], sort_keys=True) for x in piezas]
    assert len(vistas) == len(set(vistas))
    assert len({x['panel']['id'] for x in piezas}) == len(piezas)


def test_piezas_iguales_tienen_cada_una_su_etiqueta():
    x = una_pieza(lambda x: x['de'] == 2)
    hermanas = [y for y in claves.piezas(GRONDONA) if {**y['clave'], 'copia': 0} == {**x['clave'], 'copia': 0}]
    assert [y['copia'] for y in hermanas] == [1, 2]
    assert hermanas[0]['panel']['id'] != hermanas[1]['panel']['id']


def test_la_clave_sigue_aunque_cambie_el_resto_del_proyecto():
    """Versión nueva: otro orden de paneles, otra fila del .ocp, piezas nuevas y otra medida: la etiqueta sigue
    encontrando su pieza."""
    x = una_pieza(lambda x: x['panel']['num'])
    nuevo = copy.deepcopy(GRONDONA)
    nuevo['paneles'].reverse()
    for p in nuevo['paneles']:
        if p['id'] == x['panel']['id']:
            p['pieza'] = '999'; p['med'] = [100, 50, 18]
    nuevo['paneles'].append({**nuevo['paneles'][0], 'id': 'zzz|nueva', 'nombre': 'Pieza nueva', 'pieza': '1000'})
    encontrada = claves.buscar_pieza(nuevo, x['clave'])
    assert encontrada['panel']['id'] == x['panel']['id'] and encontrada['panel']['med'] == [100, 50, 18]


def test_pieza_renombrada_o_sacada_ya_no_esta():
    x = una_pieza(lambda x: x['panel']['num'])
    renombrada = copy.deepcopy(GRONDONA)
    for p in renombrada['paneles']:
        if p['id'] == x['panel']['id']:
            p['nombre'] = 'Otro nombre'
    sacada = {**GRONDONA, 'paneles': [p for p in GRONDONA['paneles'] if p['id'] != x['panel']['id']]}
    assert claves.buscar_pieza(renombrada, x['clave']) is None
    assert claves.buscar_pieza(sacada, x['clave']) is None


def test_muebles_cuentan_sus_piezas():
    m = claves.muebles(GRONDONA)
    assert sum(m.values()) == len(claves.piezas(GRONDONA))


# ---------------------------------------------------------------- PDF

def paginas(contenido):
    return len(re.findall(rb'/Type /Page\b(?!s)', contenido))


@pytest.mark.parametrize('nombre', sorted(pdf.FORMATOS))
def test_pdf_en_cada_formato(nombre):
    f = pdf.FORMATOS[nombre]
    piezas = [pdf.etiqueta_de_pieza(x['panel'], 'cocina grondona', f'https://x/a/e/{i:08d}', x['copia'], x['de'])
              for i, x in enumerate(claves.piezas(GRONDONA)[:30])]
    salida = pdf.generar(piezas, f)
    assert salida.startswith(b'%PDF')
    esperadas = -(-30 // f.por_hoja)
    assert paginas(salida) == esperadas


def test_hoja_empezada():
    f = pdf.FORMATOS['a4-3x8']
    piezas = [pdf.etiqueta_de_pieza(x['panel'], 'p', 'https://x/a/e/AAAAAAAA') for x in claves.piezas(GRONDONA)[:4]]
    assert paginas(pdf.generar(piezas, f, desde=22)) == 2          # 3 lugares libres en la primera hoja


# ---------------------------------------------------------------- códigos

def test_mismo_codigo_para_la_misma_pieza(t, pa):
    x = una_pieza()
    e1, e2 = etiqueta(t.A, pa, x), etiqueta(t.A, pa, x)
    assert e1.pk == e2.pk and len(e1.codigo) == 8 and set(e1.codigo) <= set(ALFABETO)
    assert etiqueta(t.A, pa, una_pieza(lambda y: y['clave'] != x['clave'])).codigo != e1.codigo


def test_el_codigo_es_del_proyecto_y_no_de_la_version(t, pa):
    x = una_pieza()
    e = etiqueta(t.A, pa, x)
    guardar_version(t.A, pa, GRONDONA, 2)
    assert etiqueta(t.A, pa, x).codigo == e.codigo


# ---------------------------------------------------------------- abrir la etiqueta

def test_qr_de_pieza_abre_esa_pieza_en_el_visor(cliente_de, t, pa):
    x = una_pieza(lambda x: x['de'] == 2)
    e = etiqueta(t.A, pa, x)
    c = cliente_de(t.armador_a)
    r = c.get(f'/taller-a/e/{e.codigo}')
    assert r.status_code == 302
    assert r['Location'].startswith(f'/taller-a/visor/?p={pa.pk}&pz=')
    assert c.get(f'/taller-a/visor/api/etiqueta/{e.codigo}').json() == {
        'proyecto': pa.pk, 'tipo': 'pieza', 'panel': x['panel']['id'], 'copia': x['copia'], 'de': 2}
    # el código se puede escribir en minúsculas
    assert c.get(f'/taller-a/e/{e.codigo.lower()}').status_code == 302


def test_qr_de_mueble_y_de_bulto(cliente_de, t, pa):
    mueble = next(iter(claves.muebles(GRONDONA)))
    e = etiqueta(t.A, pa, mueble=mueble)
    c = cliente_de(t.armador_a)
    for ruta in (f'/taller-a/e/{e.codigo}', f'/taller-a/e/{e.codigo}/2'):
        r = c.get(ruta)
        assert r.status_code == 302 and f'p={pa.pk}&m=' in r['Location']
    assert c.get(f'/taller-a/visor/api/etiqueta/{e.codigo}').json()['mueble'] == mueble


def test_etiqueta_vieja_avisa_que_la_pieza_ya_no_esta(cliente_de, t, pa):
    x = una_pieza(lambda x: x['panel']['num'])
    e = etiqueta(t.A, pa, x)
    sin_ella = {**GRONDONA, 'paneles': [p for p in GRONDONA['paneles'] if p['id'] != x['panel']['id']]}
    guardar_version(t.A, pa, sin_ella, 2)
    c = cliente_de(t.armador_a)
    r = c.get(f'/taller-a/e/{e.codigo}')
    assert r.status_code == 410 and 'Esta pieza ya no está en la versión actual' in r.content.decode()
    r = c.get(f'/taller-a/visor/api/etiqueta/{e.codigo}')
    assert r.status_code == 410 and 'ya no está' in r.json()['error']
    # vuelve en otra versión: la etiqueta vuelve a andar
    guardar_version(t.A, pa, GRONDONA, 3)
    assert c.get(f'/taller-a/e/{e.codigo}').status_code == 302


def test_codigo_inventado(cliente_de, t, pa):
    c = cliente_de(t.armador_a)
    assert c.get('/taller-a/e/ABCDEFGH').status_code == 404
    assert c.get('/taller-a/visor/api/etiqueta/ABCDEFGH').status_code == 404


# ---------------------------------------------------------------- separación entre talleres

def test_qr_de_otro_taller_da_404(cliente_de, t, pa):
    e = etiqueta(t.A, pa, una_pieza())
    c = cliente_de(t.dueno_b)
    # por la dirección de B (de la que sí es miembro) el código de A no existe
    assert c.get(f'/taller-b/e/{e.codigo}').status_code == 404
    assert c.get(f'/taller-b/visor/api/etiqueta/{e.codigo}').status_code == 404
    # y por la de A no entra
    assert c.get(f'/taller-a/e/{e.codigo}').status_code == 404
    assert c.get(f'/taller-a/visor/api/etiqueta/{e.codigo}').status_code == 404


def test_las_etiquetas_de_a_no_se_ven_ni_se_crean_desde_b(t, pa):
    e = etiqueta(t.A, pa, una_pieza())
    with con_taller(t.B):
        assert not Etiqueta.objects.filter(codigo=e.codigo).exists()
        assert not FormatoEtiquetas.objects.exists()
        with pytest.raises(OtroTaller):
            Etiqueta.para(pa, 'pieza', una_pieza()['clave'])        # proyecto de A desde B


def test_no_se_imprimen_etiquetas_de_un_proyecto_de_b(cliente_de, t):
    pb = proyecto_de(t.B)
    assert cliente_de(t.dueno_a).get(f'/taller-a/proyectos/{pb.pk}/etiquetas/').status_code == 404


# ---------------------------------------------------------------- entrar desde la cámara del celular

def test_sin_sesion_pide_entrar_y_vuelve_a_la_etiqueta(client, t, pa):
    e = etiqueta(t.A, pa, una_pieza())
    r = client.get(f'/taller-a/e/{e.codigo}')
    assert r.status_code == 302 and r['Location'] == f'/entrar/?next=/taller-a/e/{e.codigo}'
    html = client.get(r['Location']).content.decode()
    assert 'Contraseña o PIN' in html and f'value="/taller-a/e/{e.codigo}"' in html


def test_entrar_con_pin_vuelve_a_la_etiqueta(client, t, pa):
    e = etiqueta(t.A, pa, una_pieza())
    destino = f'/taller-a/e/{e.codigo}'
    r = client.post(f'/entrar/?next={destino}', {'username': 'arturo', 'password': '1234', 'next': destino})
    assert r.status_code == 302 and r['Location'] == destino
    assert client.get(destino).status_code == 302


@pytest.mark.parametrize('siguiente', ['https://otro.com/taller-a/e/X', '/taller-b/e/ABCDEFGH', '//otro.com/x'])
def test_el_pin_no_vuelve_a_otro_lado(client, t, siguiente):
    r = client.post('/entrar/', {'username': 'arturo', 'password': '1234', 'next': siguiente})
    assert r['Location'] == '/taller-a/'


def test_entrar_con_mail_vuelve_a_la_etiqueta(client, t, pa):
    from tests.app.ayudas import CLAVE
    e = etiqueta(t.A, pa, una_pieza())
    destino = f'/taller-a/e/{e.codigo}'
    r = client.post('/entrar/', {'username': 'dueno@a.com', 'password': CLAVE, 'next': destino})
    assert r['Location'] == destino


# ---------------------------------------------------------------- pantalla de impresión

def formulario(pa, **extra):
    datos_ = {'version': str(pa.version_actual_id), 'formato': 'a4-3x8', 'ancho': '70', 'alto': '37',
              'columnas': '3', 'filas': '8', 'margen_sup': '0', 'margen_izq': '0', 'sep_h': '0', 'sep_v': '0',
              'ajuste_x': '0', 'ajuste_y': '0', 'desde': '1'}
    datos_.update(extra)
    return datos_


def test_armador_imprime_piezas_y_bultos(cliente_de, t, pa):
    c = cliente_de(t.armador_a)
    r = c.get(f'/taller-a/proyectos/{pa.pk}/etiquetas/')
    assert r.status_code == 200 and 'Etiqueta del mueble' in r.content.decode()
    r = c.post(f'/taller-a/proyectos/{pa.pk}/etiquetas/', formulario(pa, pieza=['0', '1', '2'], mueble=['0'],
                                                                      **{'bultos-0': '3'}))
    assert r.status_code == 200 and r['Content-Type'] == 'application/pdf'
    assert paginas(r.content) == 1
    with con_taller(t.A):
        assert Etiqueta.objects.filter(tipo='pieza').count() == 3
        assert Etiqueta.objects.filter(tipo='mueble').count() == 1          # un código para los 3 bultos
        assert FormatoEtiquetas.objects.get().formato == 'a4-3x8'


def test_formato_queda_guardado(cliente_de, t, pa):
    c = cliente_de(t.dueno_a)
    c.post(f'/taller-a/proyectos/{pa.pk}/etiquetas/', formulario(pa, pieza=['0'], formato='rollo-62x40',
                                                                  ajuste_x='-1.5', bordes='on'))
    with con_taller(t.A):
        f = FormatoEtiquetas.objects.get()
    assert f.formato == 'rollo-62x40' and f.bordes and float(f.ajuste_x) == -1.5
    assert f.para_pdf().margen_izq == -1.5 and f.para_pdf().tipo == 'rollo'
    assert 'selected>Rollo térmico · 62 × 40' in c.get(f'/taller-a/proyectos/{pa.pk}/etiquetas/').content.decode()


def test_hoja_a_medida_que_no_entra(cliente_de, t, pa):
    r = cliente_de(t.dueno_a).post(f'/taller-a/proyectos/{pa.pk}/etiquetas/',
                                   formulario(pa, pieza=['0'], formato='hoja-medida', columnas='4', ancho='70'))
    assert r.status_code == 400 and 'No entran en una hoja A4' in r.content.decode()


def test_sin_elegir_nada_o_con_otra_version(cliente_de, t, pa):
    c = cliente_de(t.dueno_a)
    r = c.post(f'/taller-a/proyectos/{pa.pk}/etiquetas/', formulario(pa))
    assert r.status_code == 400 and 'Elegí al menos' in r.content.decode()
    vieja = pa.version_actual_id
    guardar_version(t.A, pa, GRONDONA, 2)
    r = c.post(f'/taller-a/proyectos/{pa.pk}/etiquetas/', formulario(pa, pieza=['0'], version=str(vieja)))
    assert r.status_code == 400 and 'otra versión' in r.content.decode()


def test_proyecto_sin_version_lista(cliente_de, t):
    with con_taller(t.A):
        p = Proyecto.objects.create(nombre='Sin convertir')
    r = cliente_de(t.dueno_a).get(f'/taller-a/proyectos/{p.pk}/etiquetas/')
    assert 'todavía no tiene una versión lista' in r.content.decode()


def test_datos_de_la_obra(cliente_de, t, pa):
    datos_obra = {'nombre': pa.nombre, 'cliente': 'Familia Pérez', 'direccion': 'Av. Siempreviva 742'}
    assert cliente_de(t.armador_a).post(f'/taller-a/proyectos/{pa.pk}/datos/', datos_obra).status_code == 403
    cliente_de(t.oficina_a).post(f'/taller-a/proyectos/{pa.pk}/datos/', datos_obra)
    pa.refresh_from_db()
    assert (pa.cliente, pa.direccion) == ('Familia Pérez', 'Av. Siempreviva 742')


def test_desde_el_visor_llega_marcada_la_pieza_o_el_mueble(cliente_de, t, pa):
    x = una_pieza(lambda x: x['de'] == 2)
    mueble = next(m for m in claves.muebles(GRONDONA) if m != x['panel']['mueble'])
    r = cliente_de(t.armador_a).get(f'/taller-a/proyectos/{pa.pk}/etiquetas/',
                                    {'pz': x['panel']['id'], 'm': mueble})
    html = r.content.decode()
    i = next(str(i) for i, y in enumerate(claves.piezas(GRONDONA)) if y['panel']['id'] == x['panel']['id'])
    j = str(list(claves.muebles(GRONDONA)).index(mueble))
    assert f'name="pieza" value="{i}" checked' in html
    assert f'name="mueble" value="{j}" checked' in html
    assert len(re.findall(r'value="\d+" checked', html)) == 2     # solo esa copia y ese mueble
    assert html.count('<details class="mueble" open>') == 2  # abiertos: el mueble de la pieza y el pedido


# ---------------------------------------------------------------- ventana "Imprimir etiqueta" del visor

def test_visor_imprime_la_pieza_elegida_con_el_formato_guardado(cliente_de, t, pa):
    x = una_pieza(lambda x: x['de'] == 2)
    copias = [y['panel']['id'] for y in claves.piezas(GRONDONA)
              if {**y['clave'], 'copia': 0} == {**x['clave'], 'copia': 0}]
    with con_taller(t.A):
        FormatoEtiquetas.objects.create(formato='rollo-62x40')
    c = cliente_de(t.armador_a)
    r = c.get('/taller-a/visor/api/etiquetas/pdf', {'proyecto': pa.pk, 'pz': copias, 'desde': '5'})
    assert r.status_code == 200 and r['Content-Type'] == 'application/pdf'
    assert paginas(r.content) == 2                          # rollo: una por página, una por copia
    with con_taller(t.A):
        assert Etiqueta.objects.filter(tipo='pieza').count() == 2
    config = c.get('/taller-a/visor/').content.decode()
    assert '"nombre": "Rollo térmico · 62 × 40 mm", "hoja": false' in config


def test_visor_imprime_los_bultos_del_mueble(cliente_de, t, pa):
    mueble = next(iter(claves.muebles(GRONDONA)))
    r = cliente_de(t.armador_a).get('/taller-a/visor/api/etiquetas/pdf',
                                     {'proyecto': pa.pk, 'm': mueble, 'bultos': '3', 'desde': '23'})
    assert r.status_code == 200
    assert paginas(r.content) == 2                          # hoja 3x8 desde la 23: 2 en la primera y 1 en otra


def test_visor_pide_algo_que_ya_no_esta(cliente_de, t, pa):
    r = cliente_de(t.armador_a).get('/taller-a/visor/api/etiquetas/pdf',
                                     {'proyecto': pa.pk, 'pz': 'no-existe', 'm': 'tampoco'})
    assert r.status_code == 400 and 'ya no está' in r.content.decode()


def test_visor_no_imprime_un_proyecto_de_b(cliente_de, t):
    pb = proyecto_de(t.B)
    r = cliente_de(t.dueno_a).get('/taller-a/visor/api/etiquetas/pdf',
                                   {'proyecto': pb.pk, 'pz': una_pieza()['panel']['id']})
    assert r.status_code == 404
