"""Ficha 18: del armado a la instalación (armado por mueble, control de calidad, instalación, Lista y 3D de entrega).

Con el proyecto.json real de *cocina grondona*, como test_avance.py."""
import json

import pytest
from django.utils import timezone

from avance import pasos as pasos_
from avance.models import (Bulto, Carga, Control, FotoDeInstalacion, Instalacion, PuntoDeControl, Ubicado,
                           puntos_de_control)
from talleres.separacion import OtroTaller, con_taller
from tests.app.test_avance import (etapas, marcar_todas, mueble_chico, piezas_del, post, qr, sin_cache, terminar,
                                   ubicaciones)
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
    terminar(c, pa, m, 2)
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
