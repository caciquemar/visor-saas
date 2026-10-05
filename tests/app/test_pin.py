"""Armadores e instaladores entran con PIN en /<taller>/pin/, desde cualquier celular."""
from datetime import timedelta

from django.utils import timezone

from talleres import pin as pines
from talleres.models import Membresia
from talleres.separacion import con_taller
from tests.app.ayudas import sumar


def entrar(client, slug, membresia, pin):
    return client.post(f'/{slug}/pin/', {'miembro': membresia.pk, 'pin': pin})


def test_alta_con_pin_y_entrar(client, t):
    client.force_login(t.dueno_a)
    r = client.post('/taller-a/equipo/alta/', {'nombre': 'Ramón', 'rol': 'armador', 'pin': '4321'})
    assert r.status_code == 302
    with con_taller(t.A):
        m = Membresia.objects.get(usuario__nombre='Ramón')
    assert m.usuario.email is None and not m.usuario.has_usable_password()
    client.logout()

    r = client.get('/taller-a/pin/')            # pública: lista los nombres
    assert r.status_code == 200 and 'Ramón' in r.text and 'Arturo' in r.text
    assert 'Bruno' not in r.text and 'Olga' not in r.text and 'Ana' not in r.text

    r = entrar(client, 'taller-a', m, '4321')
    assert r.status_code == 302 and r['Location'] == '/taller-a/'
    r = client.get('/taller-a/')
    assert r.status_code == 200 and r.wsgi_request.user == m.usuario
    assert client.session.get_expiry_age() == pines.HORAS_SESION_PIN * 3600


def test_pin_incorrecto(client, t):
    r = entrar(client, 'taller-a', t.m_armador_a, '9999')
    assert r.status_code == 400 and 'PIN incorrecto' in r.text
    assert client.get('/taller-a/').status_code == 302          # sigue sin sesión


def test_pin_de_a_en_la_pantalla_de_b(client, t):
    r = entrar(client, 'taller-b', t.m_armador_a, '1234')        # el id es de A: en B no existe
    assert r.status_code == 400
    assert client.get('/taller-b/').status_code == 302
    assert client.get('/taller-a/').status_code == 302


def test_sesion_de_pin_solo_sirve_en_su_taller(client, t):
    sumar(t.armador_a, t.B, 'armador', pin='5555')                # Arturo trabaja en los dos talleres
    assert entrar(client, 'taller-a', t.m_armador_a, '1234').status_code == 302
    assert client.get('/taller-a/').status_code == 200
    assert client.get('/taller-b/').status_code == 404            # aunque sea miembro de B
    assert 'Elegí' not in client.get('/', follow=True).text       # el inicio lo manda a A, no a elegir


def test_sesion_de_pin_no_entra_a_equipo_ni_a_la_administracion(client, t):
    entrar(client, 'taller-a', t.m_armador_a, '1234')
    assert client.get('/taller-a/equipo/').status_code == 403
    assert client.get('/admin/')['Location'].startswith('/admin/login/')


def test_si_le_cambian_el_rol_la_sesion_de_pin_deja_de_andar(client, t):
    entrar(client, 'taller-a', t.m_armador_a, '1234')
    with con_taller(t.A):
        Membresia.objects.filter(pk=t.m_armador_a.pk).update(rol='oficina')
    assert client.get('/taller-a/').status_code == 404


def test_desactivado_no_entra(client, t):
    with con_taller(t.A):
        Membresia.objects.filter(pk=t.m_armador_a.pk).update(activa=False)
    assert entrar(client, 'taller-a', t.m_armador_a, '1234').status_code == 400


def test_salir_vuelve_a_la_pantalla_de_pin(client, t):
    entrar(client, 'taller-a', t.m_armador_a, '1234')
    r = client.post('/salir/')
    assert r['Location'] == '/taller-a/pin/'
    assert client.get('/taller-a/').status_code == 302


def test_dueno_y_oficina_no_entran_con_pin(client, t):
    sumar(t.dueno_b, t.A, 'oficina')
    with con_taller(t.A):
        m = Membresia.objects.get(usuario=t.dueno_b)
        m.pin = t.m_armador_a.pin                                 # aunque tuviera un PIN cargado
        m.save()
    assert entrar(client, 'taller-a', m, '1234').status_code == 400


def test_bloqueo_progresivo(client, t):
    m = t.m_armador_a
    for _ in range(pines.FALLOS_PAUSA):
        assert 'PIN incorrecto' in entrar(client, 'taller-a', m, '0000').text
    r = entrar(client, 'taller-a', m, '1234')                     # correcto, pero en pausa
    assert r.status_code == 400 and '15 minutos' in r.text

    for _ in range(pines.FALLOS_BLOQUEO - pines.FALLOS_PAUSA):
        with con_taller(t.A):
            Membresia.objects.filter(pk=m.pk).update(pin_bloqueado_hasta=timezone.now() - timedelta(seconds=1))
        entrar(client, 'taller-a', m, '0000')
    with con_taller(t.A):
        Membresia.objects.filter(pk=m.pk).update(pin_bloqueado_hasta=None)
    r = entrar(client, 'taller-a', m, '1234')
    assert r.status_code == 400 and 'desbloquee' in r.text        # bloqueado del todo

    client.force_login(t.dueno_a)
    client.post(f'/taller-a/equipo/{m.pk}/', {'accion': 'desbloquear'})
    client.logout()
    assert entrar(client, 'taller-a', m, '1234').status_code == 302


def test_limite_por_ip(client, t, monkeypatch):
    monkeypatch.setattr(pines, 'FALLOS_POR_IP', 3)
    otro = sumar(t.dueno_b, t.A, 'instalador', pin='7777')
    for _ in range(3):
        entrar(client, 'taller-a', t.m_armador_a, '0000')
    r = entrar(client, 'taller-a', otro, '7777')
    assert r.status_code == 400 and 'este celular' in r.text
    assert entrar(client, 'taller-b', t.m_armador_b, '1234').status_code == 302   # el límite es por taller


def test_dueno_cambia_el_pin(client, t):
    client.force_login(t.oficina_a)
    client.post(f'/taller-a/equipo/{t.m_armador_a.pk}/', {'accion': 'pin', 'pin': '8642'})
    client.logout()
    assert entrar(client, 'taller-a', t.m_armador_a, '1234').status_code == 400
    assert entrar(client, 'taller-a', t.m_armador_a, '8642').status_code == 302


def test_pin_tiene_que_ser_numerico(client, t):
    client.force_login(t.dueno_a)
    client.post('/taller-a/equipo/alta/', {'nombre': 'Malo', 'rol': 'armador', 'pin': '12ab'})
    client.post('/taller-a/equipo/alta/', {'nombre': 'Corto', 'rol': 'armador', 'pin': '12'})
    with con_taller(t.A):
        assert not Membresia.objects.filter(usuario__nombre__in=['Malo', 'Corto']).exists()
