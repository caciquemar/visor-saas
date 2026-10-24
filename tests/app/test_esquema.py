"""Ficha 19: el esquema en la etiqueta del mueble (etiquetas/esquema.py y el PDF), con *cocina grondona* (en L)."""
from etiquetas import pdf
from etiquetas.claves import muebles
from etiquetas.esquema import esquema, frente_del_mueble
from etiquetas.models import FormatoEtiquetas
from talleres.separacion import con_taller
from tests.app.test_etiquetas import GRONDONA, proyecto_de

COSTADO = 'bajo pileta 2p gola 72x18'          # contra la pared del costado: mira hacia +x
PARED = 'columna 2 cajones + horno + micro gola'   # en la pared principal: mira hacia +z


def test_el_frente_es_el_del_mueble():
    assert frente_del_mueble(GRONDONA, COSTADO) == (1.0, 0.0)
    assert frente_del_mueble(GRONDONA, PARED) == (0.0, 1.0)
    assert frente_del_mueble(GRONDONA, 'no existe') == (0.0, 1.0)


def test_esquema_del_mueble_y_del_proyecto():
    solo = esquema(GRONDONA, COSTADO)
    assert solo and all(x['del_mueble'] for x in solo)
    # visto de frente, el bajo del costado es ancho (1 m) y no profundo (0,58 m)
    ancho = max(x['caja'][2] for x in solo) - min(x['caja'][0] for x in solo)
    assert 950 < ancho < 1050
    todo = esquema(GRONDONA, COSTADO, todo=True)
    assert len(todo) > len(solo) and sum(x['del_mueble'] for x in todo) == len(solo)
    # solo lo de alrededor: nada a más de 1,5 m de cada lado del mueble
    u0 = min(x['caja'][0] for x in solo) - 1500
    u1 = max(x['caja'][2] for x in solo) + 1500
    assert all(x['caja'][2] > u0 and x['caja'][0] < u1 for x in todo)
    assert esquema(GRONDONA, 'no existe') == []


def test_pdf_con_cada_opcion():
    cuenta = muebles(GRONDONA)
    for opcion in ('mueble', 'proyecto', 'ninguno'):
        dibujo = None if opcion == 'ninguno' else esquema(GRONDONA, PARED, opcion == 'proyecto')
        et = [pdf.etiqueta_de_mueble(PARED, 'cocina grondona', 'https://x/t/e/ABCDEFGH/1', cuenta[PARED], 1, 2,
                                     'Cliente', 'Calle 1', dibujo)]
        for formato in ('a4-3x8', 'rollo-62x40', 'rollo-100x50'):
            assert pdf.generar(et, pdf.FORMATOS[formato]).startswith(b'%PDF')


def test_la_opcion_queda_guardada_y_llega_al_pdf(cliente_de, t):
    pa = proyecto_de(t.A)
    c = cliente_de(t.armador_a)
    pagina = c.get(f'/taller-a/proyectos/{pa.pk}/etiquetas/').content.decode()
    assert 'Proyecto con el mueble marcado' in pagina
    with con_taller(t.A):
        f = FormatoEtiquetas.objects.first() or FormatoEtiquetas()
        f.esquema = 'proyecto'
        f.save()
        assert f.para_pdf().esquema == 'proyecto'
    r = c.get('/taller-a/visor/api/etiquetas/pdf', {'proyecto': pa.pk, 'm': PARED, 'bultos': 2})
    assert r.status_code == 200 and r['Content-Type'] == 'application/pdf'
