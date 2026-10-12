"""Entrar lo más simple posible (decisión 2026-10-12): sesión de 30 días, celular que recuerda, huella (llaves de
acceso) solo en celulares propios y link de entrada por WhatsApp."""
import hashlib
import json
import os
import re
import struct
from datetime import timedelta

import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from django.conf import settings
from django.test import Client
from django.utils import timezone
from webauthn.helpers import bytes_to_base64url as b64

from talleres import equipo_celular, llaves
from talleres.models import LinkDeEntrada
from talleres.separacion import con_taller
from tests.app.ayudas import CLAVE, marcar_celular
from usuarios.models import LlaveDeAcceso


class AutenticadorFalso:
    """Hace de celular con huella: crea una llave P-256 y firma como lo haría el navegador (WebAuthn)."""

    def __init__(self, rp_id='testserver', origen='http://testserver'):
        self.clave = ec.generate_private_key(ec.SECP256R1())
        self.id, self.rp_id, self.origen, self.contador = os.urandom(16), rp_id, origen, 0

    def _datos_cliente(self, tipo, desafio):
        return json.dumps({'type': tipo, 'challenge': desafio, 'origin': self.origen}).encode()

    def _rp(self):
        return hashlib.sha256(self.rp_id.encode()).digest()

    def crear(self, opciones):
        n = self.clave.public_key().public_numbers()
        cose = cbor2.dumps({1: 2, 3: -7, -1: 1, -2: n.x.to_bytes(32, 'big'), -3: n.y.to_bytes(32, 'big')})
        datos = (self._rp() + bytes([0x01 | 0x04 | 0x40]) + struct.pack('>I', 0) + bytes(16)
                 + struct.pack('>H', len(self.id)) + self.id + cose)
        cd = self._datos_cliente('webauthn.create', opciones['challenge'])
        return {'id': b64(self.id), 'rawId': b64(self.id), 'type': 'public-key', 'clientExtensionResults': {},
                'response': {'clientDataJSON': b64(cd), 'transports': ['internal'],
                             'attestationObject': b64(cbor2.dumps({'fmt': 'none', 'attStmt': {}, 'authData': datos}))}}

    def firmar(self, opciones, verificado=True):
        self.contador += 1
        datos = self._rp() + bytes([0x01 | (0x04 if verificado else 0)]) + struct.pack('>I', self.contador)
        cd = self._datos_cliente('webauthn.get', opciones['challenge'])
        firma = self.clave.sign(datos + hashlib.sha256(cd).digest(), ec.ECDSA(hashes.SHA256()))
        return {'id': b64(self.id), 'rawId': b64(self.id), 'type': 'public-key', 'clientExtensionResults': {},
                'response': {'clientDataJSON': b64(cd), 'authenticatorData': b64(datos), 'signature': b64(firma)}}


def registrar(client, aut, siguiente='/taller-a/'):
    o = client.post('/cuenta/llave/nueva/opciones/', content_type='application/json')
    assert o.status_code == 200, o.content
    return client.post(f'/cuenta/llave/nueva/guardar/?next={siguiente}', aut.crear(o.json()),
                       content_type='application/json')


def entrar_con_llave(client, aut, usuario=None, **kw):
    o = client.post('/cuenta/llave/entrar/opciones/', {'usuario': usuario} if usuario else {},
                    content_type='application/json').json()
    return client.post('/cuenta/llave/entrar/', aut.firmar(o, **kw), content_type='application/json')


def entrar(client, usuario, clave):
    return client.post('/entrar/', {'username': usuario, 'password': clave})


def con_llave(client, usuario):
    """Deja a `usuario` con una llave registrada en un celular propio. Devuelve el autenticador."""
    marcar_celular(client, 'propio')
    client.force_login(usuario)
    aut = AutenticadorFalso()
    assert registrar(client, aut).status_code == 200
    client.logout()
    return aut


# ---------------------------------------------------------------- sesión

def test_la_sesion_dura_30_dias_y_se_renueva(client, t):
    assert settings.SESSION_COOKIE_AGE == 30 * 24 * 3600 and settings.SESSION_SAVE_EVERY_REQUEST
    entrar(client, 'arturo', '1234')
    assert client.session.get_expiry_age() == 30 * 24 * 3600
    entrar(client, 'dueno@a.com', CLAVE)
    assert client.session.get_expiry_age() == 30 * 24 * 3600


def test_cambiar_de_persona_con_la_sesion_abierta(cliente_de, t):
    c = cliente_de(t.dueno_a)
    assert c.get('/entrar/').status_code == 302                    # ya está adentro
    assert 'Mail o usuario' in c.get('/entrar/?cambiar=1').text     # "Cambiar de persona" (menú)
    r = c.post('/entrar/?cambiar=1', {'username': 'arturo', 'password': '1234'})   # el form va a la misma dirección
    assert r.status_code == 302
    assert c.get('/taller-a/').wsgi_request.user == t.armador_a


# ---------------------------------------------------------------- celular que recuerda

def test_celular_nuevo_pregunta_de_quien_es_una_sola_vez(client, t):
    marcar_celular(client, None)
    assert 'Arturo' not in client.get('/entrar/').text             # no recuerda a nadie hasta que se entra
    r = entrar(client, 'arturo', '1234')
    assert r['Location'] == '/cuenta/celular/?next=%2Ftaller-a%2F'
    assert '¿De quién es este celular?' in client.get(r['Location']).text
    r = client.post('/cuenta/celular/', {'tipo': 'taller', 'next': '/taller-a/'})
    assert r['Location'] == '/taller-a/'
    client.post('/salir/')
    html = client.get('/entrar/').text
    assert 'Arturo' in html and 'con PIN' in html and 'con huella' not in html
    assert entrar(client, 'arturo', '1234')['Location'] == '/taller-a/'      # ya no pregunta


def test_recuerda_a_los_que_entraron_el_ultimo_primero(client, t):
    entrar(client, 'arturo', '1234')
    client.post('/salir/')
    entrar(client, 'dueno@a.com', CLAVE)
    client.post('/salir/')
    html = client.get('/entrar/').text
    assert html.index('Ana') < html.index('Arturo')
    assert 'data-entra="dueno@a.com"' in html and 'data-entra="arturo"' in html
    assert 'Bruno' not in html                                     # solo los que entraron acá


def test_quitar_de_este_celular(client, t):
    marcar_celular(client, 'taller', [t.armador_a.pk, t.dueno_a.pk])
    client.post('/cuenta/celular/olvidar/', {'usuario': t.armador_a.pk})
    html = client.get('/entrar/').text
    assert 'Arturo' not in html and 'Ana' in html


def test_cookie_tocada_se_ignora(client, t):
    client.cookies[equipo_celular.COOKIE] = json.dumps({'tipo': 'propio', 'ids': [t.dueno_a.pk]})   # sin firma
    assert 'Ana' not in client.get('/entrar/').text
    marcar_celular(client, 'taller', [t.armador_b.pk])
    valor = client.cookies[equipo_celular.COOKIE].value
    client.cookies[equipo_celular.COOKIE] = valor.replace(str(t.armador_b.pk), str(t.dueno_a.pk), 1)
    assert 'Ana' not in client.get('/entrar/').text


def test_desactivado_no_aparece(client, t):
    marcar_celular(client, 'taller', [t.armador_a.pk])
    t.armador_a.is_active = False
    t.armador_a.save()
    assert 'Arturo' not in client.get('/entrar/').text


# ---------------------------------------------------------------- huella (llaves de acceso)

def test_en_un_celular_del_taller_nunca_se_ofrece_la_huella(client, t):
    client.force_login(t.armador_a)
    assert client.get('/cuenta/llave/nueva/?next=/taller-a/')['Location'] == '/taller-a/'
    assert client.post('/cuenta/llave/nueva/opciones/', content_type='application/json').status_code == 403
    LlaveDeAcceso.objects.create(usuario=t.armador_a, credencial='x', clave_publica=b'x')
    client.logout()
    marcar_celular(client, 'taller', [t.armador_a.pk])
    html = client.get('/entrar/').text
    assert 'con PIN' in html and 'data-huella=""' in html


def test_celular_propio_ofrece_la_huella_y_entra_con_ella(client, t):
    marcar_celular(client, None)
    r = entrar(client, 'dueno@a.com', CLAVE)
    r = client.post('/cuenta/celular/', {'tipo': 'propio', 'next': '/'})
    assert r['Location'] == '/cuenta/llave/nueva/?next=%2F'
    assert 'Usar la huella' in client.get(r['Location']).text
    aut = AutenticadorFalso()
    r = registrar(client, aut, '/')
    assert r.status_code == 200 and r.json() == {'ir': '/'}
    assert t.dueno_a.llaves.count() == 1
    client.post('/salir/')

    assert 'con huella' in client.get('/entrar/').text
    r = entrar_con_llave(client, aut, usuario=t.dueno_a.pk)
    assert r.status_code == 200, r.content
    assert client.get('/taller-a/').wsgi_request.user == t.dueno_a
    assert t.dueno_a.llaves.get().contador == 1


def test_la_huella_da_una_sesion_completa(client, t):
    """La huella es más segura que el PIN: no queda atada a un taller (igual pide ser miembro de cada uno)."""
    aut = con_llave(client, t.armador_a)
    entrar_con_llave(client, aut)                                  # sin decir quién: llave descubrible
    assert client.session.get('pin_taller') is None
    assert client.get('/taller-a/').status_code == 200
    assert client.get('/taller-b/').status_code == 404             # no es de B


def test_sin_verificar_al_usuario_no_entra(client, t):
    aut = con_llave(client, t.armador_a)
    assert entrar_con_llave(client, aut, verificado=False).status_code == 403
    assert client.get('/taller-a/').status_code == 302


def test_llave_que_no_esta_registrada(client, t):
    assert entrar_con_llave(client, AutenticadorFalso()).status_code == 403


def test_desafio_vencido_o_de_otra_sesion(client, t, monkeypatch):
    aut = con_llave(client, t.armador_a)
    o = client.post('/cuenta/llave/entrar/opciones/', content_type='application/json').json()
    otro = Client()
    assert otro.post('/cuenta/llave/entrar/', aut.firmar(o), content_type='application/json').status_code == 400
    monkeypatch.setattr(llaves, 'VENCE_SEGUNDOS', -1)
    assert entrar_con_llave(client, aut).status_code == 400
    monkeypatch.setattr(llaves, 'VENCE_SEGUNDOS', 300)
    o = client.post('/cuenta/llave/entrar/opciones/', content_type='application/json').json()
    firmada = aut.firmar(o)
    assert client.post('/cuenta/llave/entrar/', firmada, content_type='application/json').status_code == 200
    client.post('/salir/')
    assert client.post('/cuenta/llave/entrar/', firmada, content_type='application/json').status_code == 400


def test_otro_origen_no_sirve(client, t):
    aut = con_llave(client, t.armador_a)
    aut.origen = 'https://trucho.com'
    assert entrar_con_llave(client, aut).status_code == 403


def test_desactivado_no_entra_con_la_huella(client, t):
    aut = con_llave(client, t.armador_a)
    t.armador_a.is_active = False
    t.armador_a.save()
    assert entrar_con_llave(client, aut).status_code == 403


def test_quitar_huellas_en_equipo(client, t):
    aut = con_llave(client, t.armador_a)
    client.force_login(t.oficina_a)
    assert 'Quitar huellas' in client.get(f'/taller-a/equipo/{t.m_armador_a.pk}/').text
    client.post(f'/taller-a/equipo/{t.m_armador_a.pk}/', {'accion': 'quitar_llaves'})
    assert not t.armador_a.llaves.exists()
    client.logout()
    assert entrar_con_llave(client, aut).status_code == 403


# ---------------------------------------------------------------- link de entrada por WhatsApp

def crear_link(client, quien, membresia):
    client.force_login(quien)
    r = client.post(f'/taller-a/equipo/{membresia.pk}/', {'accion': 'link_entrada'})
    client.logout()
    m = re.search(r'http://testserver(/cuenta/entrada/[^/"]+/)', r.text)
    return r, (m.group(1) if m else None)


def test_link_de_entrada(client, t):
    r, link = crear_link(client, t.dueno_a, t.m_armador_a)
    assert link and 'https://wa.me/?text=' in r.text and 'Mandar por WhatsApp' in r.text
    celular = Client()
    r = celular.get(link)                                          # la vista previa de WhatsApp: no entra
    assert r.status_code == 200 and 'Hola, Arturo' in r.text and 'Taller A' in r.text
    assert celular.get('/taller-a/').status_code == 302
    r = celular.post(link)
    assert r['Location'] == '/cuenta/llave/nueva/?next=%2Ftaller-a%2F'     # ofrece la huella
    assert equipo_celular.leer(celular.get('/').wsgi_request) == {'tipo': 'propio', 'ids': [t.armador_a.pk]}
    assert celular.get('/taller-a/').wsgi_request.user == t.armador_a
    assert celular.session.get('pin_taller') is None
    assert Client().post(link).status_code == 404                  # una sola vez
    assert Client().get(link).status_code == 404


def test_link_de_a_no_da_acceso_a_b(client, t):
    _, link = crear_link(client, t.dueno_a, t.m_armador_a)
    celular = Client()
    celular.post(link)
    assert celular.get('/taller-b/').status_code == 404


def test_link_vencido_o_reemplazado(client, t):
    _, viejo = crear_link(client, t.oficina_a, t.m_armador_a)
    _, nuevo = crear_link(client, t.oficina_a, t.m_armador_a)
    assert Client().post(viejo).status_code == 404                  # uno nuevo anula el anterior
    with con_taller(t.A):
        LinkDeEntrada.objects.filter(usado__isnull=True).update(vence=timezone.now() - timedelta(minutes=1))
    assert Client().post(nuevo).status_code == 404


def test_link_de_quien_ya_no_esta(client, t):
    _, link = crear_link(client, t.dueno_a, t.m_armador_a)
    with con_taller(t.A):
        t.m_armador_a.activa = False
        t.m_armador_a.save()
    assert Client().post(link).status_code == 404


@pytest.mark.parametrize('rol', ['dueno', 'oficina'])
def test_no_hay_link_para_quien_entra_con_mail(client, t, rol):
    membresia = t.m_dueno_a if rol == 'dueno' else t.m_oficina_a
    r, link = crear_link(client, t.dueno_a, membresia)
    assert link is None and 'Crear link de entrada' not in r.text
    with con_taller(t.A):
        assert not LinkDeEntrada.objects.exists()


def test_armador_no_crea_links(client, t):
    client.force_login(t.armador_a)
    assert client.post(f'/taller-a/equipo/{t.m_armador_a.pk}/', {'accion': 'link_entrada'}).status_code == 403
