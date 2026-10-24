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


def test_los_fijos_se_renombran_apagan_y_mueven_pero_no_se_borran(cliente_de, t):
    c = cliente_de(t.dueno_a)
    i = ids(t.A)
    guardar(c, t.A, {f'nombre-{i["Armado"]}': 'Ensamble', f'activa-{i["Control de calidad"]}': None},
            orden=[i['Embalaje'], i['Mecanizada'], i['Cortada'], i['Canteada']])
    nombres = [x[0] for x in los_procesos(t.A)]
    assert nombres[:4] == ['Embalaje', 'Mecanizada', 'Cortada', 'Canteada']        # todos se ordenan
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
    # Armado es la que se llama así (no la última: en el NAS la última era "Instalacion")
    assert [x[:2] for x in a] == [('Cortada', 'pieza'), ('Canteada', 'pieza'), ('Armada', 'armado'), ('Lustre', 'pieza'),
                                  ('Control de calidad', 'control'), ('Embalaje', 'embalaje'), ('Carga', 'carga'),
                                  ('Instalar en obra', 'instalacion')]
    assert [x[0] for x in b if x[1] == 'armado'] == ['Armada']


def test_migracion_sin_etapa_de_armado_y_reparacion(t):
    """0004 con un taller cuyas etapas no tienen armado: lo crea. 0006: un Armado que en realidad era otra etapa
    ("Instalacion", como quedó en el NAS) vuelve a ser del taller por pieza, con sus marcas, y se crea Armado."""
    import importlib
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    apps = MigrationExecutor(connection).loader.project_state(('avance', '0006_reparar_armado')).apps
    m4 = importlib.import_module('avance.migrations.0004_procesos_fijos')
    m6 = importlib.import_module('avance.migrations.0006_reparar_armado')
    with con_taller(t.A):
        for i, n in enumerate(['Cortado', 'Cantos', 'Instalacion'], 1):
            Etapa.objects.create(nombre=n, orden=i)
    m4.procesos_fijos(apps, None)
    assert ('Instalacion', 'pieza', False, True) in los_procesos(t.A)
    assert [x[0] for x in los_procesos(t.A) if x[1] == 'armado'] == ['Armado']
    # como quedó en el NAS con la 0004 vieja
    with con_taller(t.B):
        for i, n in enumerate(['Cortado', 'Instalacion'], 1):
            Etapa.objects.create(nombre=n, orden=i, tipo='armado' if n == 'Instalacion' else 'pieza', por_mueble=n == 'Instalacion')
    m6.reparar(apps, None)
    b = los_procesos(t.B)
    assert ('Instalacion', 'pieza', False, True) in b and [x[0] for x in b if x[1] == 'armado'] == ['Armado']
    assert [x[0] for x in los_procesos(t.A) if x[1] == 'armado'] == ['Armado']          # A ya estaba bien


# ---------------------------------------------------------------- escanear es el registro, sin correlatividad

from avance import pasos as pasos_  # noqa: E402
from avance.models import Bulto, Carga, Marca  # noqa: E402
from tests.app.test_avance import mueble_chico, piezas_del, post, qr  # noqa: E402
from tests.app.test_etiquetas import etiqueta  # noqa: E402


def apagar(cliente, taller, *nombres):
    i = ids(taller)
    guardar(cliente, taller, {f'activa-{i[n]}': None for n in nombres})


def paso(taller, proyecto, mueble):
    with con_taller(taller):
        return pasos_.pasos(proyecto)['muebles'][mueble]['paso']


def test_embalar_al_escanear_ya_y_cambiar_bultos(cliente_de, t, pa):
    m = mueble_chico()
    c = cliente_de(t.armador_a)
    e = qr(etiqueta(t.A, pa, mueble=m))
    d = post(c, '/taller-a/puesto/api/embalar', {'texto': e}).json()
    assert d['resultado'] == 'ok' and d['fin']['bultos'] == 1
    assert post(c, '/taller-a/puesto/api/embalar', {'texto': e}).json()['resultado'] == 'ya'
    d = post(c, '/taller-a/puesto/api/bultos', {'proyecto': pa.pk, 'mueble': m, 'bultos': 3}).json()
    assert [b['numero'] for b in d['fin']['lista']] == [1, 2, 3]
    d = post(c, '/taller-a/puesto/api/bultos', {'proyecto': pa.pk, 'mueble': m, 'bultos': 2}).json()
    assert d['fin']['bultos'] == 2 and len(d['fin']['lista']) == 2
    # con un bulto cargado ya no se cambia
    c.post(f'/taller-a/proyectos/{pa.pk}/cargas/nueva/', {'todo': '1'})
    with con_taller(t.A):
        carga = Carga.objects.get()
    post(c, f'/taller-a/puesto/api/cargas/{carga.pk}/bulto', {'texto': qr(etiqueta(t.A, pa, mueble=m), 1)})
    assert post(c, '/taller-a/puesto/api/bultos', {'proyecto': pa.pk, 'mueble': m, 'bultos': 1}).status_code == 409


def test_cargar_un_mueble_sin_embalar_lo_embala_con_un_bulto(cliente_de, t, pa):
    m = mueble_chico()
    c = cliente_de(t.armador_a)
    c.post(f'/taller-a/proyectos/{pa.pk}/cargas/nueva/', {'todo': '1'})
    with con_taller(t.A):
        carga = Carga.objects.get()
    pieza = piezas_del(m)[0]
    d = post(c, f'/taller-a/puesto/api/cargas/{carga.pk}/bulto', {'texto': etiqueta(t.A, pa, pieza).codigo}).json()
    assert d['resultado'] == 'ok' and d['numero'] == 1 and d['de'] == 1
    assert paso(t.A, pa, m) == 'cargado'


def test_procesos_apagados(cliente_de, t, pa):
    m = mueble_chico()
    apagar(cliente_de(t.dueno_a), t.A, 'Control de calidad', 'Embalaje', 'Instalar en obra')
    c = cliente_de(t.armador_a)              # el mismo cliente, ahora como armador
    e = qr(etiqueta(t.A, pa, mueble=m))
    for ruta in ('control', 'embalar', 'instalar'):
        r = post(c, f'/taller-a/puesto/api/{ruta}', {'texto': e})
        assert r.status_code == 400 and 'apagado' in r.json()['error'], ruta
    with con_taller(t.A):
        assert [p[0] for p in pasos_.pasos_activos()] == ['sin_armar', 'armado', 'cargado', 'entregado']
    # sin embalaje se carga igual (1 bulto por mueble) y, sin instalación, salir a obra entrega
    c.post(f'/taller-a/proyectos/{pa.pk}/cargas/nueva/', {'todo': '0', 'mueble': [m]})
    with con_taller(t.A):
        carga = Carga.objects.get()
    assert post(c, f'/taller-a/puesto/api/cargas/{carga.pk}/bulto', {'texto': e}).json()['resultado'] == 'ok'
    c.post(f'/taller-a/cargas/{carga.pk}/', {'motivo': ''})
    with con_taller(t.A):
        carga.refresh_from_db()
        assert carga.estado == 'entregada' and Bulto.objects.get().estado == 'entregado'
        assert carga.bultos.get().fin.motivo == 'Sin embalaje'
    assert paso(t.A, pa, m) == 'entregado'
    # Mi puesto no los ofrece
    pagina = c.get('/taller-a/puesto/').content.decode()
    assert '"Embalaje"' not in pagina and '"Control de calidad"' not in pagina and '"Carga"' in pagina


def test_proceso_propio_por_mueble(cliente_de, t, pa):
    m = mueble_chico()
    cliente_de(t.dueno_a).post('/taller-a/procesos/', {'accion': 'agregar-etapas', 'nombre': 'Lustre', 'por': 'mueble'})
    c = cliente_de(t.armador_a)
    lustre = ids(t.A)['Lustre']
    d = post(c, '/taller-a/puesto/api/armar', {'texto': qr(etiqueta(t.A, pa, mueble=m)), 'etapa': lustre}).json()
    assert d['resultado'] == 'ok' and d['etapa'] == 'Lustre' and d['nuevas'] == len(piezas_del(m))
    d = post(c, '/taller-a/puesto/api/armar', {'texto': qr(etiqueta(t.A, pa, mueble=m)), 'etapa': lustre}).json()
    assert d['resultado'] == 'ya' and d['ya']['por'] == 'Arturo'
    with con_taller(t.A):
        assert Marca.objects.filter(etapa_id=lustre, mueble=m).count() == len(piezas_del(m))
    # uno por pieza no se marca así
    r = post(c, '/taller-a/puesto/api/armar', {'texto': qr(etiqueta(t.A, pa, mueble=m)), 'etapa': ids(t.A)['Cortada']})
    assert r.status_code == 400


# ---------------------------------------------------------------- anotaciones

def test_anotaciones_con_y_sin_tarea_y_fotos(cliente_de, t, pa):
    from avance.models import Anotacion
    from tests.app.test_trabajos import imagen
    from trabajos.models import Trabajo
    m = mueble_chico()
    x = piezas_del(m)[0]
    c = cliente_de(t.armador_a)
    armado = ids(t.A)['Armado']
    d = post(c, '/taller-a/puesto/api/anotar', {'proyecto': pa.pk, 'mueble': m, 'proceso': armado,
                                                'texto': 'Quedó un poco descuadrado'}).json()
    sin = d['anotacion']
    assert sin['tarea'] is None and sin['proceso'] == 'Armado' and sin['por'] == 'Arturo' and sin['panel'] == ''
    d = post(c, '/taller-a/puesto/api/anotar', {'proyecto': pa.pk, 'mueble': m, 'panel': x['panel']['id'],
                                                'texto': 'Canto despegado', 'tarea': True}).json()
    con = d['anotacion']
    with con_taller(t.A):
        tarea = Trabajo.objects.get(pk=con['tarea'])
    assert tarea.piezas == [x['panel']['id']] and tarea.texto == 'Canto despegado' and con['pieza']
    # la foto queda en la anotación y en su tarea
    r = c.post(f'/taller-a/puesto/api/anotaciones/{con["id"]}/fotos', imagen(), content_type='image/jpeg')
    foto = r.json()['foto']
    assert c.get(f'/taller-a/puesto/api/fotos-de-anotacion/{foto}').status_code == 200
    with con_taller(t.A):
        assert tarea.fotos.count() == 1
    # se ven en la Lista y en lo que lee el visor
    muebles = c.get(f'/taller-a/visor/api/entrega?proyecto={pa.pk}').json()['muebles']
    assert [a['texto'] for a in muebles[m]['anotaciones']] == ['Canto despegado', 'Quedó un poco descuadrado']
    assert 'Canto despegado' in c.get(f'/taller-a/proyectos/{pa.pk}/entrega/').content.decode()
    assert post(c, '/taller-a/puesto/api/anotar', {'proyecto': pa.pk, 'mueble': m, 'texto': ''}).status_code == 400
    # desde B no se ven ni se tocan
    cb = cliente_de(t.dueno_b)
    assert cb.get(f'/taller-b/puesto/api/fotos-de-anotacion/{foto}').status_code == 404
    assert post(cb, '/taller-b/puesto/api/anotar', {'proyecto': pa.pk, 'mueble': m, 'texto': 'x'}).status_code == 404
    with con_taller(t.B):
        assert not Anotacion.objects.exists()


# ---------------------------------------------------------------- ficha 20: avance de un proceso (Lista y 3D)

def test_avance_de_un_proceso(cliente_de, t, pa):
    m = mueble_chico()
    c = cliente_de(t.armador_a)
    i = ids(t.A)
    post(c, '/taller-a/puesto/api/armar', {'texto': qr(etiqueta(t.A, pa, mueble=m)), 'etapa': i['Armado']})
    d = c.get(f'/taller-a/visor/api/avance-proceso?proyecto={pa.pk}&proceso={i["Armado"]}').json()
    assert d['muebles'][m]['estado'] == 'hecho' and d['totales']['hecho'] == 1 and not d['por_pieza']
    corte = i['Cortada']
    post(c, '/taller-a/puesto/api/marcar', {'texto': etiqueta(t.A, pa, piezas_del(m)[0]).codigo, 'etapa': corte})
    d = c.get(f'/taller-a/visor/api/avance-proceso?proyecto={pa.pk}&proceso={corte}').json()
    assert d['por_pieza'] and d['muebles'][m]['estado'] == 'parcial' and sum(d['paneles'].values()) == 1
    html = c.get(f'/taller-a/proyectos/{pa.pk}/entrega/?proceso={i["Armado"]}').content.decode()
    assert 'Avance: Armado' in html and f'avance={i["Armado"]}' in html
    assert cliente_de(t.dueno_b).get(f'/taller-b/visor/api/avance-proceso?proyecto={pa.pk}&proceso={corte}').status_code == 404
