"""Ficha 23: Equipo con personas y roles propios con permisos. Dueño pasó a llamarse Administrador."""
import importlib

from django.core import mail

from talleres.models import Invitacion, Membresia, Rol, Taller
from talleres.permisos import BASES
from talleres.separacion import con_taller
from tests.app.ayudas import rol_pk, sumar
from usuarios.models import Usuario


def un_rol(taller, nombre, permisos, con_pin=False):
    with con_taller(taller):
        return Rol.objects.create(nombre=nombre, permisos=permisos, con_pin=con_pin, orden=9)


def test_cada_taller_arranca_con_los_cuatro_roles(db):
    t = Taller.objects.create(nombre='Nuevo', slug='nuevo')
    with con_taller(t):
        assert [(r.base, r.nombre, r.con_pin) for r in Rol.objects.all()] == [
            ('admin', 'Administrador', False), ('oficina', 'Oficina', False), ('armador', 'Armador', True),
            ('instalador', 'Instalador', True)]


def test_la_migracion_da_los_mismos_accesos_de_antes():
    m = importlib.import_module('talleres.migrations.0006_pasar_a_roles')
    assert [(b, n, p, list(ps)) for b, n, p, ps in m.BASES] == [(b, n, p, list(ps)) for b, n, p, ps in BASES]


def test_los_accesos_iniciales_son_los_de_antes(cliente_de, t):
    o = cliente_de(t.oficina_a)
    assert o.get('/taller-a/equipo/').status_code == 200
    assert o.get('/taller-a/marca/').status_code == 403
    assert o.get('/taller-a/equipo/roles/nuevo/').status_code == 403
    a = cliente_de(t.armador_a)
    assert a.get('/taller-a/puesto/').status_code == 200 and a.get('/taller-a/materiales/').status_code == 403
    d = cliente_de(t.dueno_a)
    assert d.get('/taller-a/marca/').status_code == 200 and d.get('/taller-a/equipo/?ver=roles').status_code == 200


def test_un_rol_propio_ve_solo_lo_suyo(cliente_de, t):
    panolero = un_rol(t.A, 'Pañolero', ['puesto'], con_pin=True)
    otro = Usuario.objects.create_user(None, nombre='Pedro')
    sumar(otro, t.A, panolero, pin='2580')
    c = cliente_de(otro)
    menu = [x['nombre'] for x in c.get('/taller-a/puesto/').context['menu']]
    assert menu == ['Inicio', 'Producción', 'Mi puesto']
    for pagina in ('/taller-a/visor/', '/taller-a/proyectos/', '/taller-a/trabajos/', '/taller-a/tablero/',
                   '/taller-a/equipo/'):
        assert c.get(pagina).status_code == 403, pagina


def test_abm_de_roles(cliente_de, t):
    c = cliente_de(t.dueno_a)
    r = c.post('/taller-a/equipo/roles/nuevo/', {'nombre': 'Pañolero', 'con_pin': 'on', 'permisos': ['puesto', 'tablero']})
    assert r.status_code == 302
    with con_taller(t.A):
        rol = Rol.objects.get(nombre='Pañolero')
    assert rol.con_pin and rol.permisos == ['puesto', 'tablero'] and rol.base == ''
    # con PIN no puede manejar Equipo, Roles, Marca ni borrar proyectos
    r = c.post(f'/taller-a/equipo/roles/{rol.pk}/', {'nombre': 'Pañolero', 'con_pin': 'on', 'permisos': ['equipo']})
    assert r.status_code == 400 and 'PIN' in r.text
    # nombre repetido
    assert c.post('/taller-a/equipo/roles/nuevo/', {'nombre': 'oficina'}).status_code == 400
    # con una persona no se borra; sin nadie, sí
    otro = Usuario.objects.create_user(None, nombre='Pedro')
    m = sumar(otro, t.A, rol, pin='2580')
    c.post(f'/taller-a/equipo/roles/{rol.pk}/', {'accion': 'borrar'})
    with con_taller(t.A):
        assert Rol.objects.filter(pk=rol.pk).exists()
        m.delete()
    c.post(f'/taller-a/equipo/roles/{rol.pk}/', {'accion': 'borrar'})
    with con_taller(t.A):
        assert not Rol.objects.filter(pk=rol.pk).exists()


def test_el_administrador_no_se_edita_ni_se_borra(cliente_de, t):
    admin = rol_pk(t.A, 'admin')
    c = cliente_de(t.dueno_a)
    c.post(f'/taller-a/equipo/roles/{admin}/', {'nombre': 'Jefe', 'permisos': []})
    with con_taller(t.A):
        r = Rol.objects.get(pk=admin)
    assert r.nombre == 'Jefe' and r.es_admin and r.puede('marca')          # se renombra, sigue pudiendo todo
    assert c.post(f'/taller-a/equipo/roles/{admin}/', {'accion': 'borrar'}).status_code == 403


def test_sacarle_el_pin_a_un_rol_con_gente_sin_mail_no_se_puede(cliente_de, t):
    c = cliente_de(t.dueno_a)
    armador = rol_pk(t.A, 'armador')
    r = c.post(f'/taller-a/equipo/roles/{armador}/', {'nombre': 'Armador', 'permisos': ['puesto']})
    assert r.status_code == 400
    with con_taller(t.A):
        assert Rol.objects.get(pk=armador).con_pin


def test_agregar_persona_con_mail_o_con_pin(cliente_de, t):
    c = cliente_de(t.oficina_a)
    # con mail: invitación
    c.post('/taller-a/equipo/agregar/', {'nombre': 'Nora', 'rol': rol_pk(t.A, 'oficina'), 'email': 'nora@a.com'})
    assert mail.outbox[-1].to == ['nora@a.com'] and 'como oficina' in mail.outbox[-1].body
    # sin mail: solo en un rol con PIN
    r = c.post('/taller-a/equipo/agregar/', {'nombre': 'Pepe', 'rol': rol_pk(t.A, 'oficina'), 'entra': 'pin',
                                             'pin': '1357'})
    assert r.status_code == 400 and 'no entra con PIN' in r.text
    c.post('/taller-a/equipo/agregar/', {'nombre': 'Pepe', 'rol': rol_pk(t.A, 'armador'), 'entra': 'pin',
                                         'pin': '1357'})
    with con_taller(t.A):
        assert Membresia.objects.get(usuario__nombre='Pepe').rol.base == 'armador'
    # la oficina no da el rol Administrador
    assert c.post('/taller-a/equipo/agregar/', {'nombre': 'Jefe', 'rol': rol_pk(t.A, 'admin'),
                                                'email': 'jefe@a.com'}).status_code == 400


def test_desactivar_y_reactivar(cliente_de, t):
    c = cliente_de(t.oficina_a)
    armador = rol_pk(t.A, 'armador')
    c.post(f'/taller-a/equipo/{t.m_armador_a.pk}/', {'accion': 'guardar', 'rol': armador})
    t.m_armador_a.refresh_from_db()
    assert not t.m_armador_a.activa
    assert 'Inactivo' in c.get('/taller-a/equipo/').text
    c.post(f'/taller-a/equipo/{t.m_armador_a.pk}/', {'accion': 'guardar', 'rol': armador, 'activa': 'on'})
    t.m_armador_a.refresh_from_db()
    assert t.m_armador_a.activa
    # sin mail no puede tener un rol que no entra con PIN (no podría entrar)
    c.post(f'/taller-a/equipo/{t.m_armador_a.pk}/', {'accion': 'guardar', 'rol': rol_pk(t.A, 'oficina'), 'activa': 'on'})
    t.m_armador_a.refresh_from_db()
    assert t.m_armador_a.rol.base == 'armador'


def test_anular_una_invitacion(cliente_de, t):
    c = cliente_de(t.oficina_a)
    c.post('/taller-a/equipo/agregar/', {'nombre': 'Nora', 'rol': rol_pk(t.A, 'oficina'), 'email': 'nora@a.com'})
    with con_taller(t.A):
        inv = Invitacion.objects.get()
    c.post(f'/taller-a/equipo/invitacion/{inv.pk}/anular/')
    with con_taller(t.A):
        assert not Invitacion.objects.get().vigente
    assert '<td>nora@a.com</td>' not in c.get('/taller-a/equipo/').text


def test_roles_de_otro_taller_ni_se_ven_ni_se_asignan(cliente_de, t):
    rol_b = un_rol(t.B, 'Secreto de B', ['puesto'])
    c = cliente_de(t.dueno_a)
    assert 'Secreto de B' not in c.get('/taller-a/equipo/?ver=roles').text
    assert c.get(f'/taller-a/equipo/roles/{rol_b.pk}/').status_code == 404
    r = c.post(f'/taller-a/equipo/{t.m_armador_a.pk}/', {'accion': 'guardar', 'rol': rol_b.pk, 'activa': 'on'})
    t.m_armador_a.refresh_from_db()
    assert t.m_armador_a.rol.base == 'armador'
    assert c.post('/taller-a/equipo/agregar/', {'nombre': 'X', 'rol': rol_b.pk, 'email': 'x@a.com'}).status_code == 400
