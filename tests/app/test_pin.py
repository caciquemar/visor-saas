"""Armadores e instaladores entran en /entrar/ (la misma pantalla que el mail) con su usuario y PIN, desde
cualquier celular."""
from datetime import timedelta

from django.utils import timezone

from talleres import pin as pines
from talleres.models import Membresia
from talleres.separacion import con_taller
from tests.app.ayudas import sumar
from usuarios.models import Usuario


def entrar(client, usuario, pin, siguiente=None):
    datos = {'username': usuario, 'password': pin}
    if siguiente:
        datos['next'] = siguiente
    return client.post('/entrar/', datos)


def entro(r):
    return r.status_code == 302


def test_los_que_no_tienen_mail_tienen_usuario(t):
    assert t.armador_a.usuario == 'arturo' and t.armador_b.usuario == 'bruno'
    assert t.dueno_a.usuario is None                              # con mail no hace falta
    otro = Usuario.objects.create_user(None, nombre='Arturo')
    assert otro.usuario == 'arturo2'                              # no se repite
    assert Usuario.objects.create_user(None, nombre='Ñoño Pérez').usuario == 'nono-perez'


def test_alta_con_pin_y_entrar(client, t):
    client.force_login(t.dueno_a)
    r = client.post('/taller-a/equipo/alta/', {'nombre': 'Ramón', 'rol': 'armador', 'pin': '4321'})
    assert r.status_code == 302
    with con_taller(t.A):
        m = Membresia.objects.get(usuario__nombre='Ramón')
    assert m.usuario.email is None and not m.usuario.has_usable_password()
    assert m.usuario.usuario == 'ramon'
    assert 'ramon' in client.get('/taller-a/equipo/').text        # Equipo muestra con qué entra
    client.logout()

    r = entrar(client, 'Ramon', '4321')                            # sin importar mayúsculas
    assert r.status_code == 302 and r['Location'] == '/taller-a/'
    r = client.get('/taller-a/')
    assert r.status_code == 200 and r.wsgi_request.user == m.usuario
    assert client.session.get_expiry_age() == 30 * 24 * 3600              # como todas las sesiones


def test_alta_con_usuario_elegido(client, t):
    client.force_login(t.dueno_a)
    client.post('/taller-a/equipo/alta/', {'nombre': 'Ramón', 'usuario': 'Ramon.P', 'rol': 'instalador',
                                           'pin': '4321'})
    assert Usuario.objects.get(nombre='Ramón').usuario == 'ramon.p'
    r = client.post('/taller-a/equipo/alta/', {'nombre': 'Otro', 'usuario': 'bruno', 'rol': 'armador',
                                               'pin': '4321'}, follow=True)
    assert 'ya existe' in r.text                                   # bruno es de B: los usuarios no se repiten
    assert not Usuario.objects.filter(nombre='Otro').exists()
    r = client.post('/taller-a/equipo/alta/', {'nombre': 'Malo', 'usuario': 'con espacio', 'rol': 'armador',
                                               'pin': '4321'}, follow=True)
    assert not Usuario.objects.filter(nombre='Malo').exists()


def test_cambiar_nombre_y_usuario_en_equipo(client, t):
    client.force_login(t.oficina_a)
    html = client.get(f'/taller-a/equipo/{t.m_armador_a.pk}/').text
    assert 'value="Arturo"' in html and 'value="arturo"' in html          # muestra los datos actuales
    client.post(f'/taller-a/equipo/{t.m_armador_a.pk}/',
                {'accion': 'datos', 'nombre': 'Arturo Gómez', 'usuario': 'arturo.g'})
    t.armador_a.refresh_from_db()
    assert (t.armador_a.nombre, t.armador_a.usuario) == ('Arturo Gómez', 'arturo.g')
    assert 'Arturo Gómez' in client.get('/taller-a/equipo/').text
    r = client.post(f'/taller-a/equipo/{t.m_armador_a.pk}/', {'accion': 'datos', 'nombre': 'X', 'usuario': 'bruno'})
    assert 'ya existe' in r.text
    t.armador_a.refresh_from_db()
    assert t.armador_a.nombre == 'Arturo Gómez'
    client.logout()
    assert not entro(entrar(client, 'arturo', '1234'))
    assert entro(entrar(client, 'arturo.g', '1234'))


def test_los_datos_de_quien_tiene_mail_no_se_cambian_en_equipo(client, t):
    client.force_login(t.dueno_a)
    assert 'Guardar datos' not in client.get(f'/taller-a/equipo/{t.m_oficina_a.pk}/').text
    client.post(f'/taller-a/equipo/{t.m_oficina_a.pk}/', {'accion': 'datos', 'nombre': 'Otra', 'usuario': 'otra'})
    t.oficina_a.refresh_from_db()
    assert t.oficina_a.nombre == 'Olga'


def test_mail_y_pin_en_la_misma_pantalla(client, t):
    from tests.app.ayudas import CLAVE
    html = client.get('/entrar/').text
    assert 'Mail o usuario' in html and 'Contraseña o PIN' in html
    assert entro(entrar(client, 'dueno@a.com', CLAVE))
    assert client.get('/taller-a/equipo/').status_code == 200
    client.logout()
    assert entro(entrar(client, 'arturo', '1234'))
    assert client.get('/taller-a/equipo/').status_code == 403


def test_pin_incorrecto(client, t):
    r = entrar(client, 'arturo', '9999')
    assert not entro(r) and 'Usuario o PIN incorrectos' in r.text
    assert client.get('/taller-a/').status_code == 302            # sigue sin sesión


def test_usuario_inexistente_responde_igual(client, t):
    r = entrar(client, 'nadie', '1234')
    assert not entro(r) and 'Usuario o PIN incorrectos' in r.text


def test_la_pantalla_vieja_de_pin_lleva_a_entrar(client, t):
    r = client.get('/taller-a/pin/')
    assert r.status_code == 302 and r['Location'] == '/entrar/?next=%2Ftaller-a%2F'
    assert 'Arturo' not in client.get(r['Location']).text          # ya no se ven los nombres sin sesión


def test_sesion_de_pin_solo_sirve_en_su_taller(client, t):
    sumar(t.armador_a, t.B, 'armador', pin='5555')                # Arturo trabaja en los dos talleres
    assert entrar(client, 'arturo', '1234')['Location'] == '/taller-a/'
    assert client.get('/taller-a/').status_code == 200
    assert client.get('/taller-b/').status_code == 404            # aunque sea miembro de B
    assert 'Elegí' not in client.get('/', follow=True).text       # el inicio lo manda a A, no a elegir
    client.post('/salir/')
    assert entrar(client, 'arturo', '5555')['Location'] == '/taller-b/'   # con el PIN de B, entra en B
    assert client.get('/taller-a/').status_code == 404


def test_con_dos_talleres_vuelve_al_que_pide_next(client, t):
    sumar(t.armador_a, t.B, 'armador', pin='1234')                # mismo PIN en los dos
    assert entrar(client, 'arturo', '1234', '/taller-b/trabajos/')['Location'] == '/taller-b/trabajos/'
    client.post('/salir/')
    assert entrar(client, 'arturo', '1234', '/taller-a/trabajos/')['Location'] == '/taller-a/trabajos/'


def test_next_de_otro_taller_lleva_al_suyo(client, t):
    assert entrar(client, 'arturo', '1234', '/taller-b/trabajos/')['Location'] == '/taller-a/'


def test_sesion_de_pin_no_entra_a_equipo_ni_a_la_administracion(client, t):
    entrar(client, 'arturo', '1234')
    assert client.get('/taller-a/equipo/').status_code == 403
    assert client.get('/admin/')['Location'].startswith('/admin/login/')


def test_si_le_cambian_el_rol_la_sesion_de_pin_deja_de_andar(client, t):
    entrar(client, 'arturo', '1234')
    with con_taller(t.A):
        Membresia.objects.filter(pk=t.m_armador_a.pk).update(rol='oficina')
    assert client.get('/taller-a/').status_code == 404


def test_desactivado_no_entra(client, t):
    with con_taller(t.A):
        Membresia.objects.filter(pk=t.m_armador_a.pk).update(activa=False)
    assert not entro(entrar(client, 'arturo', '1234'))


def test_salir_vuelve_a_entrar(client, t):
    entrar(client, 'arturo', '1234')
    r = client.post('/salir/')
    assert r['Location'] == '/entrar/'
    assert client.get('/taller-a/').status_code == 302


def test_entrar_con_mail_despues_de_pin_no_queda_atado(client, t):
    from tests.app.ayudas import CLAVE
    sumar(t.dueno_a, t.B, 'oficina')
    entrar(client, 'arturo', '1234')
    entrar(client, 'dueno@a.com', CLAVE)
    assert client.get('/taller-b/').status_code == 200
    assert client.session.get('pin_taller') is None


def test_dueno_y_oficina_no_entran_con_pin(client, t):
    t.dueno_b.usuario = 'beto'
    t.dueno_b.save()
    sumar(t.dueno_b, t.A, 'oficina')
    with con_taller(t.A):
        m = Membresia.objects.get(usuario=t.dueno_b)
        m.pin = t.m_armador_a.pin                                 # aunque tuviera un PIN cargado
        m.save()
    assert not entro(entrar(client, 'beto', '1234'))


def test_bloqueo_progresivo(client, t):
    m = t.m_armador_a
    for _ in range(pines.FALLOS_PAUSA):
        assert 'PIN incorrectos' in entrar(client, 'arturo', '0000').text
    r = entrar(client, 'arturo', '1234')                           # correcto, pero en pausa
    assert not entro(r) and '15 minutos' in r.text

    for _ in range(pines.FALLOS_BLOQUEO - pines.FALLOS_PAUSA):
        with con_taller(t.A):
            Membresia.objects.filter(pk=m.pk).update(pin_bloqueado_hasta=timezone.now() - timedelta(seconds=1))
        entrar(client, 'arturo', '0000')
    with con_taller(t.A):
        Membresia.objects.filter(pk=m.pk).update(pin_bloqueado_hasta=None)
    r = entrar(client, 'arturo', '1234')
    assert not entro(r) and 'desbloquee' in r.text                # bloqueado del todo

    client.force_login(t.dueno_a)
    client.post(f'/taller-a/equipo/{m.pk}/', {'accion': 'desbloquear'})
    client.logout()
    assert entro(entrar(client, 'arturo', '1234'))


def test_limite_por_ip(client, t, monkeypatch):
    monkeypatch.setattr(pines, 'FALLOS_POR_IP', 3)
    for usuario in ('arturo', 'nadie', 'bruno'):                  # cuentan también los usuarios que no existen
        entrar(client, usuario, '0000')
    r = entrar(client, 'bruno', '1234')
    assert not entro(r) and 'este celular' in r.text              # vale para todos los talleres


def test_dueno_cambia_el_pin(client, t):
    client.force_login(t.oficina_a)
    client.post(f'/taller-a/equipo/{t.m_armador_a.pk}/', {'accion': 'pin', 'pin': '8642'})
    client.logout()
    assert not entro(entrar(client, 'arturo', '1234'))
    assert entro(entrar(client, 'arturo', '8642'))


def test_pin_tiene_que_ser_numerico(client, t):
    client.force_login(t.dueno_a)
    client.post('/taller-a/equipo/alta/', {'nombre': 'Malo', 'rol': 'armador', 'pin': '12ab'})
    client.post('/taller-a/equipo/alta/', {'nombre': 'Corto', 'rol': 'armador', 'pin': '12'})
    with con_taller(t.A):
        assert not Membresia.objects.filter(usuario__nombre__in=['Malo', 'Corto']).exists()


def test_en_el_celular_compartido_el_siguiente_entra_sin_salir(client, t):
    from tests.app.ayudas import sumar as _sumar
    otro = Usuario.objects.create_user(None, nombre='Raúl')
    _sumar(otro, t.A, 'instalador', pin='2468')
    entrar(client, 'arturo', '1234')
    assert 'Contraseña o PIN' in client.get('/entrar/').text       # no lo manda de vuelta al taller
    assert entro(entrar(client, 'raul', '2468'))
    assert client.get('/taller-a/').wsgi_request.user == otro
