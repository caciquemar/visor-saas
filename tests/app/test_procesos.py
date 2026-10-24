"""Ficha 19: todos los procesos en una lista (los del taller, por pieza o por mueble, y los fijos que se apagan),
escanear es el registro, anotaciones.

Con el proyecto.json real de *cocina grondona*, como test_avance.py."""
import pytest

from avance.models import Etapa, procesos
from talleres.separacion import con_taller
from tests.app.test_avance import sin_cache
from tests.app.test_etiquetas import proyecto_de

sin_cache = sin_cache


@pytest.fixture
def pa(t):
    return proyecto_de(t.A)


def los_procesos(taller):
    with con_taller(taller):
        return [(e.nombre, e.tipo, e.por_mueble, e.activa) for e in procesos()]


def ids(taller):
    with con_taller(taller):
        return {e.nombre: e.pk for e in procesos()}


# ---------------------------------------------------------------- Procesos

def test_procesos_por_defecto(t):
    assert los_procesos(t.A) == [
        ('Cortada', 'pieza', False, True), ('Canteada', 'pieza', False, True), ('Mecanizada', 'pieza', False, True),
        ('Armado', 'armado', True, True), ('Control de calidad', 'control', True, True),
        ('Embalaje', 'embalaje', True, True), ('Carga', 'carga', True, True),
        ('Instalar en obra', 'instalacion', True, True)]


def guardar(c, taller, cambios=None, orden=None):
    """POST de la tabla de Procesos con todo como está, más `cambios` ({campo: valor}; None borra el campo)."""
    with con_taller(taller):
        datos = {'accion': 'guardar-etapas'}
        for e in procesos():
            datos[f'nombre-{e.pk}'] = e.nombre
            if e.activa:
                datos[f'activa-{e.pk}'] = '1'
            if not e.fijo:
                datos[f'por-{e.pk}'] = 'mueble' if e.por_mueble else 'pieza'
    for k, v in (cambios or {}).items():
        if v is None:
            datos.pop(k, None)
        else:
            datos[k] = v
    if orden:
        datos['orden'] = ','.join(map(str, orden))
    return c.post('/taller-a/procesos/', datos)


def test_los_fijos_se_renombran_y_apagan_pero_no_se_borran_ni_mueven(cliente_de, t):
    c = cliente_de(t.dueno_a)
    i = ids(t.A)
    guardar(c, t.A, {f'nombre-{i["Armado"]}': 'Ensamble', f'activa-{i["Control de calidad"]}': None},
            orden=[i['Embalaje'], i['Mecanizada'], i['Cortada'], i['Canteada']])
    nombres = [x[0] for x in los_procesos(t.A)]
    assert nombres == ['Mecanizada', 'Cortada', 'Canteada', 'Ensamble', 'Control de calidad', 'Embalaje', 'Carga',
                       'Instalar en obra']
    assert [x[3] for x in los_procesos(t.A) if x[1] == 'control'] == [False]
    c.post('/taller-a/procesos/', {'accion': f'borrar-etapas-{i["Carga"]}'})
    assert 'Carga' in [x[0] for x in los_procesos(t.A)]
    c.post('/taller-a/procesos/', {'accion': f'borrar-etapas-{i["Cortada"]}'})       # sin usar: se borra
    assert 'Cortada' not in [x[0] for x in los_procesos(t.A)]


def test_agregar_proceso_por_mueble_y_cambiarlo(cliente_de, t):
    c = cliente_de(t.dueno_a)
    c.post('/taller-a/procesos/', {'accion': 'agregar-etapas', 'nombre': 'Lustre', 'por': 'mueble'})
    assert ('Lustre', 'pieza', True, True) in los_procesos(t.A)
    # va con los del taller, antes de los fijos
    assert [x[0] for x in los_procesos(t.A)].index('Lustre') == 3
    guardar(c, t.A, {f'por-{ids(t.A)["Lustre"]}': 'pieza'})
    assert ('Lustre', 'pieza', False, True) in los_procesos(t.A)
    assert 'Se marca por' in c.get('/taller-a/procesos/').content.decode()


def test_al_menos_un_proceso_prendido(cliente_de, t):
    c = cliente_de(t.dueno_a)
    guardar(c, t.A, {f'activa-{i}': None for i in ids(t.A).values()})
    assert [x[0] for x in los_procesos(t.A) if x[3]] == ['Armado']


def test_un_fijo_de_cada_tipo_por_taller(t):
    from django.db import IntegrityError, transaction
    procesos_a = los_procesos(t.A)
    with con_taller(t.A):
        with pytest.raises(IntegrityError), transaction.atomic():
            Etapa.objects.create(nombre='Otro armado', tipo='armado')
    assert los_procesos(t.B)[3][1] == 'armado' and procesos_a[3][1] == 'armado'       # cada taller el suyo


def test_migracion_de_etapas_viejas(t):
    """0004: en cada taller, la última etapa prendida (la que hacía de armado) pasa a ser el fijo Armado, con sus marcas,
    y se suman los otros cuatro. Con dos talleres y varias etapas (el distinct no tiene que repetir talleres)."""
    import importlib
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    migracion = importlib.import_module('avance.migrations.0004_procesos_fijos')
    apps = MigrationExecutor(connection).loader.project_state(('avance', '0004_procesos_fijos')).apps
    for taller, apagada in ((t.A, False), (t.B, True)):
        with con_taller(taller):
            for i, n in enumerate(['Cortada', 'Canteada', 'Armada', 'Lustre'], 1):
                Etapa.objects.create(nombre=n, orden=i, activa=not (apagada and n == 'Lustre'))
    migracion.procesos_fijos(apps, None)
    a, b = los_procesos(t.A), los_procesos(t.B)
    assert [x[:2] for x in a] == [('Cortada', 'pieza'), ('Canteada', 'pieza'), ('Armada', 'pieza'), ('Lustre', 'armado'),
                                  ('Control de calidad', 'control'), ('Embalaje', 'embalaje'), ('Carga', 'carga'),
                                  ('Instalar en obra', 'instalacion')]
    # en B la última estaba apagada: Armado es la última prendida
    assert [x[0] for x in b if x[1] == 'armado'] == ['Armada']
