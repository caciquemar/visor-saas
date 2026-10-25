"""Mi cuenta (/<taller>/cuenta/): cada uno ve y cambia sus propios datos."""
from django.contrib.auth.hashers import check_password

from talleres.models import Membresia
from talleres.separacion import con_taller
from tests.app.ayudas import CLAVE
from usuarios.models import LlaveDeAcceso


def test_pide_login_y_ser_del_taller(client, cliente_de, t):
    assert client.get('/taller-a/cuenta/').status_code == 302
    assert cliente_de(t.dueno_b).get('/taller-a/cuenta/').status_code in (403, 404)


def test_cambiar_nombre_mail_y_contrasena(cliente_de, t):
    c = cliente_de(t.oficina_a)
    html = c.get('/taller-a/cuenta/').content.decode()
    assert 'oficina@a.com' in html and 'Cambiar la contraseña' in html and 'Tu PIN' not in html
    assert 'Mi cuenta' in html                                       # en el menú ☰
    c.post('/taller-a/cuenta/', {'accion': 'datos', 'nombre': 'Olga Pérez'})
    t.oficina_a.refresh_from_db()
    assert t.oficina_a.nombre == 'Olga Pérez'
    # el mail pide la contraseña y no puede ser el de otra cuenta
    assert c.post('/taller-a/cuenta/', {'accion': 'mail', 'email': 'olga@a.com', 'actual': 'mal'}).status_code == 400
    assert c.post('/taller-a/cuenta/', {'accion': 'mail', 'email': 'dueno@a.com', 'actual': CLAVE}).status_code == 400
    c.post('/taller-a/cuenta/', {'accion': 'mail', 'email': ' Olga@A.com ', 'actual': CLAVE})
    t.oficina_a.refresh_from_db()
    assert t.oficina_a.email == 'olga@a.com'
    # la contraseña: con la actual, y la sesión sigue abierta
    nueva = 'Otra-clave-larga-2026'
    r = c.post('/taller-a/cuenta/', {'accion': 'clave', 'old_password': CLAVE, 'new_password1': nueva,
                                     'new_password2': nueva})
    assert r.status_code == 302
    t.oficina_a.refresh_from_db()
    assert t.oficina_a.check_password(nueva)
    assert c.get('/taller-a/cuenta/').status_code == 200


def test_armador_cambia_usuario_y_pin(cliente_de, t):
    c = cliente_de(t.armador_a)
    html = c.get('/taller-a/cuenta/').content.decode()
    assert 'Tu PIN' in html and 'Cambiar la contraseña' not in html
    c.post('/taller-a/cuenta/', {'accion': 'datos', 'nombre': 'Arturo Gómez', 'usuario': 'arturo-g'})
    t.armador_a.refresh_from_db()
    assert (t.armador_a.nombre, t.armador_a.usuario) == ('Arturo Gómez', 'arturo-g')
    assert c.post('/taller-a/cuenta/', {'accion': 'pin', 'actual': '0000', 'pin': '5678',
                                        'repetido': '5678'}).status_code == 400
    assert c.post('/taller-a/cuenta/', {'accion': 'pin', 'actual': '1234', 'pin': '5678',
                                        'repetido': '5679'}).status_code == 400
    c.post('/taller-a/cuenta/', {'accion': 'pin', 'actual': '1234', 'pin': '5678', 'repetido': '5678'})
    with con_taller(t.A):
        assert check_password('5678', Membresia.objects.get(usuario=t.armador_a).pin)
    # el PIN de B no cambia (es por taller)
    with con_taller(t.B):
        assert check_password('1234', Membresia.objects.get(usuario=t.armador_b).pin)


def test_quitar_solo_sus_huellas(cliente_de, t):
    mia = LlaveDeAcceso.objects.create(usuario=t.dueno_a, credencial='a', clave_publica=b'x', equipo='Moto G')
    ajena = LlaveDeAcceso.objects.create(usuario=t.oficina_a, credencial='b', clave_publica=b'x')
    c = cliente_de(t.dueno_a)
    assert 'Moto G' in c.get('/taller-a/cuenta/').content.decode()
    c.post('/taller-a/cuenta/', {'accion': 'quitar_llave', 'llave': ajena.pk})
    c.post('/taller-a/cuenta/', {'accion': 'quitar_llave', 'llave': mia.pk})
    assert list(LlaveDeAcceso.objects.values_list('pk', flat=True)) == [ajena.pk]
