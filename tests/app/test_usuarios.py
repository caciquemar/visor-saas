"""Crear un taller, invitar por mail, aceptar, entrar con mail y contraseña, y roles dentro de Equipo."""
import re
from datetime import timedelta

from django.core import mail
from django.utils import timezone

from talleres.mails import invitar
from talleres.models import Invitacion, Membresia, Taller
from talleres.separacion import con_taller
from tests.app.ayudas import CLAVE, sumar


def link_del_mail(mensaje):
    return re.search(r'http://testserver(/cuenta/invitacion/[^/\s]+/)', mensaje.body).group(1)


def test_crear_taller_en_la_administracion_invita_al_dueno(admin_client, db):
    r = admin_client.post('/admin/talleres/taller/add/', {
        'nombre': 'Muebles Sur', 'slug': 'muebles-sur', 'activo': 'on', 'email_dueno': 'Duena@Sur.com'})
    assert r.status_code == 302, r.content
    taller = Taller.objects.get(slug='muebles-sur')
    assert len(mail.outbox) == 1 and mail.outbox[0].to == ['duena@sur.com']
    assert 'Muebles Sur' in mail.outbox[0].subject
    with con_taller(taller):
        assert Invitacion.objects.get().rol == 'dueno'
    # la ficha del taller muestra miembros e invitaciones
    r = admin_client.get(f'/admin/talleres/taller/{taller.pk}/change/')
    assert r.status_code == 200 and 'duena@sur.com' in r.text
    assert 'muebles-sur' in admin_client.get('/admin/talleres/taller/').text


def test_slug_reservado_no_se_puede_usar(admin_client, db):
    r = admin_client.post('/admin/talleres/taller/add/', {
        'nombre': 'Admin', 'slug': 'admin', 'activo': 'on', 'email_dueno': 'x@x.com'})
    assert r.status_code == 200 and 'reservado' in r.text
    assert not Taller.objects.exists()


def test_invitar_aceptar_y_entrar(client, t):
    client.force_login(t.dueno_a)
    r = client.post('/taller-a/equipo/invitar/', {'email': 'nuevo@a.com', 'rol': 'instalador'})
    assert r.status_code == 302 and len(mail.outbox) == 1
    link = link_del_mail(mail.outbox[0])
    client.logout()

    r = client.get(link)
    assert r.status_code == 200 and 'Taller A' in r.text
    r = client.post(link, {'nombre': 'Nico', 'password1': CLAVE, 'password2': CLAVE})
    assert r.status_code == 302 and r['Location'] == '/taller-a/'
    assert client.get('/taller-a/').status_code == 200
    with con_taller(t.A):
        m = Membresia.objects.get(usuario__email='nuevo@a.com')
        assert m.rol == 'instalador' and m.usuario.nombre == 'Nico'

    # El link no sirve dos veces
    client.logout()
    assert client.get(link).status_code == 404

    # Entra con mail (sin importar mayúsculas) y contraseña
    r = client.post('/entrar/', {'username': 'Nuevo@A.com', 'password': CLAVE})
    assert r.status_code == 302 and r['Location'] == '/'
    assert client.get('/')['Location'] == '/taller-a/'


def test_usuario_existente_acepta_despues_de_entrar(client, t):
    with con_taller(t.B):
        invitar(t.B, 'dueno@a.com', 'oficina')
    link = link_del_mail(mail.outbox[0])
    r = client.get(link)
    assert r.status_code == 302 and r['Location'].startswith('/entrar/')
    client.force_login(t.dueno_a)
    assert client.get(link)['Location'] == '/taller-b/'
    assert client.get('/taller-b/').status_code == 200
    assert 'Elegí el taller' in client.get('/').text        # con dos talleres, pregunta cuál


def test_invitacion_de_b_no_da_acceso_a_a(client, t):
    with con_taller(t.B):
        invitar(t.B, 'solo-b@b.com', 'oficina')
    r = client.post(link_del_mail(mail.outbox[0]), {'nombre': 'Sole', 'password1': CLAVE, 'password2': CLAVE})
    assert r['Location'] == '/taller-b/'
    assert client.get('/taller-b/').status_code == 200
    assert client.get('/taller-a/').status_code == 404


def test_invitacion_para_otra_cuenta(client, t):
    with con_taller(t.A):
        invitar(t.A, 'otra@a.com', 'oficina')
    client.force_login(t.dueno_b)
    assert client.get(link_del_mail(mail.outbox[0])).status_code == 403
    assert client.get('/taller-a/').status_code == 404


def test_invitacion_vencida_o_inventada(client, t):
    with con_taller(t.A):
        inv = invitar(t.A, 'tarde@a.com', 'oficina')
        Invitacion.objects.filter(pk=inv.pk).update(vence=timezone.now() - timedelta(minutes=1))
    assert client.get(link_del_mail(mail.outbox[0])).status_code == 404
    assert client.get('/cuenta/invitacion/inventada/').status_code == 404


def test_dueno_de_a_no_invita_en_b(cliente_de, t):
    c = cliente_de(t.dueno_a)
    assert c.post('/taller-b/equipo/invitar/', {'email': 'x@x.com', 'rol': 'dueno'}).status_code == 404
    assert c.post('/taller-b/equipo/alta/', {'nombre': 'X', 'rol': 'armador', 'pin': '1111'}).status_code == 404
    assert c.post(f'/taller-a/equipo/{t.m_armador_b.pk}/', {'accion': 'desbloquear'}).status_code == 404
    assert c.post(f'/taller-b/equipo/{t.m_armador_b.pk}/', {'accion': 'desbloquear'}).status_code == 404
    assert not mail.outbox
    with con_taller(t.B):
        assert Membresia.objects.count() == 2


def test_equipo_muestra_solo_el_taller(cliente_de, t):
    r = cliente_de(t.dueno_a).get('/taller-a/equipo/')
    assert r.status_code == 200
    assert 'Arturo' in r.text and 'Olga' in r.text
    assert 'Bruno' not in r.text and 'Beto' not in r.text


def test_armador_no_entra_a_equipo(cliente_de, t):
    assert cliente_de(t.armador_a).get('/taller-a/equipo/').status_code == 403


def test_oficina_no_hace_duenos_ni_toca_al_dueno(cliente_de, t):
    c = cliente_de(t.oficina_a)
    assert c.get('/taller-a/equipo/').status_code == 200
    c.post('/taller-a/equipo/invitar/', {'email': 'jefe@a.com', 'rol': 'dueno'})
    assert not mail.outbox
    c.post(f'/taller-a/equipo/{t.m_armador_a.pk}/', {'accion': 'guardar', 'rol': 'dueno', 'activa': 'on'})
    t.m_armador_a.refresh_from_db()
    assert t.m_armador_a.rol == 'armador'
    assert c.post(f'/taller-a/equipo/{t.m_dueno_a.pk}/', {'accion': 'guardar', 'rol': 'oficina'}).status_code == 403


def test_no_queda_un_taller_sin_dueno(cliente_de, t):
    c = cliente_de(t.dueno_a)
    c.post(f'/taller-a/equipo/{t.m_dueno_a.pk}/', {'accion': 'guardar', 'rol': 'oficina', 'activa': 'on'})
    t.m_dueno_a.refresh_from_db()
    assert t.m_dueno_a.rol == 'dueno'
    sumar(t.dueno_b, t.A, 'dueno')
    c.post(f'/taller-a/equipo/{t.m_dueno_a.pk}/', {'accion': 'guardar', 'rol': 'oficina', 'activa': 'on'})
    t.m_dueno_a.refresh_from_db()
    assert t.m_dueno_a.rol == 'oficina'


def test_olvide_la_contrasena(client, t):
    r = client.post('/cuenta/olvide/', {'email': 'dueno@a.com'})
    assert r.status_code == 302 and len(mail.outbox) == 1
    link = re.search(r'http://testserver(/cuenta/clave/\S+/)', mail.outbox[0].body).group(1)
    r = client.get(link, follow=True)
    assert r.status_code == 200
    r = client.post(r.redirect_chain[-1][0], {'new_password1': 'otra-clave-larga-1', 'new_password2': 'otra-clave-larga-1'})
    assert r.status_code == 302
    assert client.login(username='dueno@a.com', password='otra-clave-larga-1')


def test_pagina_entrar_en_castellano(client, db):
    r = client.get('/entrar/')
    assert r.status_code == 200 and 'Contraseña' in r.text and 'PIN' in r.text
