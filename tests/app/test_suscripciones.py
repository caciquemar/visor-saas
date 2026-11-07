"""Ficha 08: planes, estados de la suscripción, pago por período (pasarela simulada y Payway con respuestas falsas),
solo lectura, topes del plan y separación entre talleres."""
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.core import mail
from django.utils import timezone

from suscripciones import cotizacion, estados
from suscripciones.config import cobro as config_cobro
from suscripciones.models import Cobro, Cotizacion, Pago, Plan, Suscripcion
from suscripciones.pasarelas import Payway
from suscripciones.servicio import confirmar, nuevo_pago, revisar_taller, suscripcion_de
from talleres import limites
from talleres.separacion import con_taller

HOY = date(2026, 11, 5)


# ---------------------------------------------------------------- reglas (sin base)

def plan(clave='taller', usd=19, orden=1):
    return SimpleNamespace(clave=clave, precio_usd=Decimal(usd), orden=orden, pk=orden)


TALLER, PRO, FABRICA = plan('taller', 19, 1), plan('pro', 39, 2), plan('fabrica', 79, 3)


def susc(prueba_hasta=HOY, pagado_hasta=None, sin_cobro_hasta=None, p=TALLER):
    return SimpleNamespace(prueba_hasta=prueba_hasta, pagado_hasta=pagado_hasta, sin_cobro_hasta=sin_cobro_hasta,
                           plan=p, plan_id=p.pk, plan_proximo=None, plan_proximo_id=None, cambio_de_plan=None)


@pytest.mark.parametrize('dias, esperado', [
    (0, estados.ACTIVA), (1, estados.VENCIDA), (7, estados.VENCIDA), (8, estados.SOLO_LECTURA),
    (90, estados.SOLO_LECTURA), (91, estados.SUSPENDIDA), (180, estados.SUSPENDIDA), (181, estados.PARA_BORRAR)])
def test_estados_despues_de_lo_pagado(dias, esperado):
    s = susc(prueba_hasta=HOY - timedelta(days=60), pagado_hasta=HOY)
    assert estados.estado(s, HOY + timedelta(days=dias)) == esperado


def test_prueba_vencida_sin_pagar_va_directo_a_solo_lectura():
    s = susc(prueba_hasta=HOY)
    assert estados.estado(s, HOY) == estados.PRUEBA
    assert estados.estado(s, HOY + timedelta(days=1)) == estados.SOLO_LECTURA


def test_sin_cobro_es_activa():
    s = susc(prueba_hasta=HOY - timedelta(days=100), sin_cobro_hasta=HOY + timedelta(days=10))
    assert estados.estado(s, HOY) == estados.ACTIVA


def test_sumar_meses():
    assert estados.sumar_meses(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert estados.sumar_meses(date(2026, 11, 5), 12) == date(2027, 11, 5)


def test_precios_por_periodo():
    assert estados.precio_usd(TALLER, 'mensual') == Decimal('19.00')
    assert estados.precio_usd(TALLER, 'semestral') == Decimal('104.50')       # 5½ meses
    assert estados.precio_usd(TALLER, 'anual') == Decimal('190.00')           # 10 meses


def test_pagar_en_prueba_empieza_cuando_termina_la_prueba():
    s = susc(prueba_hasta=HOY + timedelta(days=10))
    c = estados.cotizar(s, TALLER, 'mensual', HOY)
    assert c['desde'] == HOY + timedelta(days=11)
    assert estados.estado(SimpleNamespace(**{**vars(s), 'pagado_hasta': c['hasta']}), HOY) == estados.PRUEBA


def test_renovar_sigue_desde_lo_pagado_y_vencido_desde_hoy():
    s = susc(prueba_hasta=HOY - timedelta(days=60), pagado_hasta=HOY + timedelta(days=5))
    assert estados.cotizar(s, TALLER, 'mensual', HOY)['desde'] == HOY + timedelta(days=6)
    s.pagado_hasta = HOY - timedelta(days=20)
    c = estados.cotizar(s, TALLER, 'anual', HOY)
    assert c['desde'] == HOY and c['hasta'] == date(2027, 11, 4)


def test_subir_de_plan_paga_la_diferencia_y_cambia_ya():
    s = susc(prueba_hasta=HOY - timedelta(days=60), pagado_hasta=HOY + timedelta(days=14))   # 15 días pagos
    c = estados.cotizar(s, PRO, 'mensual', HOY)
    assert c['diferencia_usd'] == Decimal('10.00')          # (39 - 19) * 15 / 30
    assert c['usd'] == Decimal('49.00') and c['inmediato']


def test_bajar_de_plan_vale_desde_el_proximo_periodo():
    s = susc(prueba_hasta=HOY - timedelta(days=60), pagado_hasta=HOY + timedelta(days=14), p=PRO)
    pago = SimpleNamespace(plan=TALLER, periodo='mensual')
    estados.aplicar_pago(s, pago, HOY)
    assert s.plan is PRO and s.plan_proximo is TALLER and s.cambio_de_plan == HOY + timedelta(days=15)
    s.plan_proximo_id = TALLER.pk
    assert estados.cambiar_plan_si_toca(s, HOY + timedelta(days=15)) and s.plan is TALLER


# ---------------------------------------------------------------- con la base

@pytest.fixture
def cobro(t):
    configurar(activo=True, pasarela='simulada')
    Cotizacion.objects.create(fecha=timezone.localdate(), ars_por_usd=Decimal('1500'))
    return t


def configurar(**campos):
    c = config_cobro()
    for k, v in campos.items():
        setattr(c, k, v)
    c.save()


def s_de(taller):
    with con_taller(taller):
        return suscripcion_de(taller)


def guardar(taller, **campos):
    with con_taller(taller):
        Suscripcion.objects.update(**campos)


def plan_db(clave):
    return Plan.objects.get(clave=clave)


def test_los_planes_vienen_con_la_migracion(db):
    assert list(Plan.objects.values_list('clave', flat=True)) == ['taller', 'pro', 'fabrica']


def test_taller_nuevo_arranca_en_prueba(cobro):
    s = s_de(cobro.A)
    assert s.plan.clave == 'pro' and s.prueba_hasta == timezone.localdate() + timedelta(days=29)
    assert estados.estado(s, timezone.localdate()) == estados.PRUEBA


def pagar(cliente, slug, plan_clave, periodo, resultado):
    r = cliente.post(f'/{slug}/suscripcion/pagar/', {'plan': plan_db(plan_clave).pk, 'periodo': periodo})
    assert r.status_code == 302 and '/pagos/simulada/' in r.url
    simulada = r.url.split('testserver', 1)[1]
    r = cliente.post(simulada, {'resultado': resultado})
    volver = r.url.split('testserver', 1)[1]
    return cliente.get(volver, follow=True)


def test_pagar_mensual_aprobado(cobro, cliente_de):
    c = cliente_de(cobro.dueno_a)
    r = pagar(c, 'taller-a', 'taller', 'mensual', 'aprobado')
    assert 'Pago aprobado' in r.content.decode()
    s = s_de(cobro.A)
    hoy = timezone.localdate()
    assert s.plan.clave == 'taller'
    assert s.pagado_hasta == estados.sumar_meses(s.prueba_hasta + timedelta(days=1), 1) - timedelta(days=1)
    with con_taller(cobro.A):
        p = Pago.objects.get()
    assert p.estado == 'aprobado' and p.monto_ars == Decimal('28500')        # 19 * 1500
    assert p.desde == s.prueba_hasta + timedelta(days=1) and hoy < p.desde


def test_pago_rechazado_no_cambia_nada(cobro, cliente_de):
    antes = s_de(cobro.A)
    r = pagar(cliente_de(cobro.dueno_a), 'taller-a', 'pro', 'anual', 'rechazado')
    assert 'rechazado' in r.content.decode()
    despues = s_de(cobro.A)
    assert despues.pagado_hasta is None and despues.plan_id == antes.plan_id
    with con_taller(cobro.A):
        assert Pago.objects.get().estado == 'rechazado'


def test_solo_lectura_frena_cambios_y_al_pagar_vuelve(cobro, cliente_de):
    guardar(cobro.A, prueba_hasta=timezone.localdate() - timedelta(days=1))      # prueba vencida, sin pagar
    c = cliente_de(cobro.dueno_a)
    assert c.get('/taller-a/notas/').status_code == 200                           # ver, sí
    r = c.post('/taller-a/notas/nueva/', {'texto': 'no'})
    assert r.status_code == 403 and 'solo lectura' in r.content.decode()
    assert c.get('/taller-a/').status_code == 200
    assert 'solo lectura' in c.get('/taller-a/').content.decode()                 # el aviso de arriba
    pagar(c, 'taller-a', 'taller', 'mensual', 'aprobado')                        # reactivación
    s = s_de(cobro.A)
    assert estados.estado(s, timezone.localdate()) == estados.ACTIVA
    assert s.pagado_hasta == estados.sumar_meses(timezone.localdate(), 1) - timedelta(days=1)
    assert c.post('/taller-a/notas/nueva/', {'texto': 'sí'}).status_code == 200


def test_gracia_deja_cambiar(cobro, cliente_de):
    hoy = timezone.localdate()
    guardar(cobro.A, prueba_hasta=hoy - timedelta(days=60), pagado_hasta=hoy - timedelta(days=3))
    assert c_post_nota(cliente_de(cobro.dueno_a)).status_code == 200


def c_post_nota(c):
    return c.post('/taller-a/notas/nueva/', {'texto': 'x'})


def test_suspendida_lleva_a_pagar_y_los_demas_no_entran(cobro, cliente_de):
    hoy = timezone.localdate()
    guardar(cobro.A, prueba_hasta=hoy - timedelta(days=200), pagado_hasta=hoy - timedelta(days=100))
    r = cliente_de(cobro.dueno_a).get('/taller-a/notas/')
    assert r.status_code == 302 and r.url.endswith('/taller-a/suscripcion/')
    assert cliente_de(cobro.dueno_a).get('/taller-a/suscripcion/').status_code == 200
    assert cliente_de(cobro.oficina_a).get('/taller-a/notas/').status_code == 403


def test_con_el_cobro_apagado_no_se_frena_nada(cobro, cliente_de):
    configurar(activo=False)
    guardar(cobro.A, prueba_hasta=timezone.localdate() - timedelta(days=200))
    assert c_post_nota(cliente_de(cobro.dueno_a)).status_code == 200
    with con_taller(cobro.A):
        assert limites.permite(cobro.A, 'fotos_de_trabajos') and limites.puede_sumar(cobro.A, 'usuarios', 100)


def test_solo_quien_maneja_la_suscripcion_la_ve(cobro, cliente_de):
    assert cliente_de(cobro.oficina_a).get('/taller-a/suscripcion/').status_code == 403
    assert cliente_de(cobro.dueno_a).get('/taller-a/suscripcion/').status_code == 200


def test_funciones_y_topes_del_plan(cobro, cliente_de):
    hoy = timezone.localdate()
    guardar(cobro.A, plan=plan_db('taller'), prueba_hasta=hoy - timedelta(days=60), pagado_hasta=hoy + timedelta(days=9))
    with con_taller(cobro.A):
        assert limites.permite(cobro.A, 'trabajos')
        assert not limites.permite(cobro.A, 'fotos_de_trabajos') and not limites.permite(cobro.A, 'avance')
        assert limites.tope(cobro.A, 'usuarios') == (3, 3)        # dueño, oficina y el armador con PIN
    r = cliente_de(cobro.dueno_a).post('/taller-a/equipo/agregar/', {'nombre': 'Nadia', 'email': 'nadia@a.com'},
                                       follow=True)
    assert 'Llegaste a las 3 personas' in r.content.decode()
    assert cliente_de(cobro.dueno_a).get('/taller-a/puesto/').status_code == 403      # Producción, solo Pro
    # en prueba rige el Pro
    guardar(cobro.A, prueba_hasta=hoy + timedelta(days=3), pagado_hasta=None)
    with con_taller(cobro.A):
        assert limites.permite(cobro.A, 'avance') and limites.tope(cobro.A, 'usuarios')[0] is None


def test_plan_editable_en_la_administracion(cobro):
    p = plan_db('taller')
    p.max_usuarios, p.funciones = 10, ['trabajos', 'avance']
    p.save()
    hoy = timezone.localdate()
    guardar(cobro.A, plan=p, prueba_hasta=hoy - timedelta(days=60), pagado_hasta=hoy + timedelta(days=9))
    with con_taller(cobro.A):
        assert limites.permite(cobro.A, 'avance') and limites.puede_sumar(cobro.A, 'usuarios')


# ---------------------------------------------------------------- aviso, revisión diaria y separación

def pago_pendiente(taller, usuario, plan_clave='taller', periodo='mensual'):
    from suscripciones.vistas import urls_de
    with con_taller(taller):
        return nuevo_pago(suscripcion_de(taller), plan_db(plan_clave), periodo, usuario, urls_de)


def test_el_aviso_consulta_y_aprueba(cobro, client):
    pago = pago_pendiente(cobro.A, cobro.dueno_a)
    with con_taller(cobro.A):
        Pago.objects.filter(pk=pago.pk).update(datos={'simulada': 'aprobado'})
    r = client.post(f'/pagos/aviso/taller-a/{pago.codigo}/', data='{"cualquier": "cosa"}',
                    content_type='application/json')
    assert r.status_code == 200
    with con_taller(cobro.A):
        assert Pago.objects.get(pk=pago.pk).estado == 'aprobado'


def test_el_aviso_solo_no_aprueba(cobro, client):
    pago = pago_pendiente(cobro.A, cobro.dueno_a)
    r = client.post(f'/pagos/aviso/taller-a/{pago.codigo}/', {'status': 'approved', 'payment_id': '123'})
    assert r.status_code == 200
    with con_taller(cobro.A):
        assert Pago.objects.get(pk=pago.pk).estado == 'pendiente'
    assert client.post('/pagos/aviso/no-existe/xx/').status_code == 200


def test_otro_taller_no_toca_el_pago(cobro, cliente_de, client):
    pago = pago_pendiente(cobro.A, cobro.dueno_a)
    assert cliente_de(cobro.dueno_b).get(f'/taller-b/suscripcion/volver/{pago.codigo}/').status_code == 404
    with con_taller(cobro.A):
        Pago.objects.filter(pk=pago.pk).update(datos={'simulada': 'aprobado'})
    client.post(f'/pagos/aviso/taller-b/{pago.codigo}/')                 # con el taller equivocado no lo encuentra
    with con_taller(cobro.A):
        assert Pago.objects.get(pk=pago.pk).estado == 'pendiente'
    with con_taller(cobro.B):
        assert not Pago.objects.exists()


def test_la_pagina_simulada_solo_existe_con_la_pasarela_simulada(cobro, client, settings):
    pago = pago_pendiente(cobro.A, cobro.dueno_a)
    configurar(pasarela='payway')
    assert client.get(f'/pagos/simulada/taller-a/{pago.codigo}/').status_code == 404
    configurar(pasarela='simulada')
    settings.PASARELA_SIMULADA_PERMITIDA = False      # el servidor (DEBUG=0): no existe aunque esté elegida
    assert client.get(f'/pagos/simulada/taller-a/{pago.codigo}/').status_code == 404


def test_la_simulada_no_se_puede_elegir_en_el_servidor(db, settings):
    from django.core.exceptions import ValidationError
    settings.PASARELA_SIMULADA_PERMITIDA = False
    c = config_cobro()
    c.pasarela = 'simulada'
    with pytest.raises(ValidationError):
        c.full_clean()


def test_la_configuracion_sale_de_la_base_y_es_una_sola(db):
    configurar(sitio='123', activo=True)
    assert Cobro.objects.count() == 1 and config_cobro().sitio == '123' and limites.activas()
    Cobro(sitio='999').save()                    # guardar otra pisa la misma fila
    assert Cobro.objects.count() == 1 and config_cobro().sitio == '999'


def test_revision_diaria_vence_links_viejos_y_avisa_una_vez(cobro):
    pago = pago_pendiente(cobro.A, cobro.dueno_a)
    with con_taller(cobro.A):
        Pago.objects.filter(pk=pago.pk).update(creado=timezone.now() - timedelta(days=3))
    hoy = timezone.localdate()
    guardar(cobro.A, prueba_hasta=hoy + timedelta(days=7))
    revisar_taller(cobro.A)
    revisar_taller(cobro.A)
    with con_taller(cobro.A):
        assert Pago.objects.get(pk=pago.pk).estado == 'vencido'
    avisos = [m for m in mail.outbox if 'vence' in m.subject]
    assert len(avisos) == 1 and avisos[0].to == ['dueno@a.com']       # la oficina no maneja la suscripción
    assert '/taller-a/suscripcion/' in avisos[0].body


def test_revision_diaria_guarda_el_estado(cobro):
    guardar(cobro.A, prueba_hasta=timezone.localdate() - timedelta(days=1))
    revisar_taller(cobro.A)
    assert s_de(cobro.A).estado == estados.SOLO_LECTURA
    assert any('solo lectura' in m.subject for m in mail.outbox)


# ---------------------------------------------------------------- Payway (sin red: respuestas falsas)

class Respuesta:
    def __init__(self, status, datos):
        self.status_code, self._datos, self.text = status, datos, str(datos)

    def json(self):
        return self._datos

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


@pytest.fixture
def payway(settings, cobro, monkeypatch):
    settings.PAYWAY_CLAVE_PRIVADA = 'privada'          # la única que queda en el .env
    configurar(pasarela='payway', ambiente='sandbox', clave_publica='publica', sitio='0001', establecimiento='123',
               cuit='20111111112')
    falso = SimpleNamespace(pedidos=[], pagos={})

    def post(url, json=None, headers=None, timeout=None):
        falso.pedidos.append(('post', url, json, headers))
        return Respuesta(200, {'payment_link': 'https://pago.payway.test/abc'})

    def get(url, headers=None, timeout=None, params=None):
        falso.pedidos.append(('get', url, params, headers))
        if url.endswith('/payments'):                     # la lista: del más viejo al más nuevo, de a pageSize
            todos = [dict(x) for x in falso.pagos.values()]
            desde, cuantos = params.get('offset', 0), params['pageSize']
            return Respuesta(200, {'results': todos[desde:desde + cuantos], 'hasMore': desde + cuantos < len(todos)})
        return Respuesta(200, dict(falso.pagos.get(url.rsplit('/', 1)[1], {})))

    import suscripciones.pasarelas as p
    monkeypatch.setattr(p.requests, 'post', post)
    monkeypatch.setattr(p.requests, 'get', get)
    return falso


def test_payway_arma_el_link(payway):
    pago = pago_pendiente(t_A(), None)
    assert pago.link == 'https://pago.payway.test/abc' and pago.pasarela == 'payway'
    _, url, cuerpo, enc = payway.pedidos[0]
    assert url == 'https://developers.decidir.com/api/v1/checkout-payment-button/link' and enc['apikey'] == 'privada'
    assert 'products' not in cuerpo and 'redirect_url' not in cuerpo        # Payway no los acepta juntos
    assert 28500 - 99 <= cuerpo['total_price'] <= 28500 - 1                # monto único: unos pesos menos
    assert cuerpo['total_price'] == float(pago.monto_ars)
    assert cuerpo['currency'] == 'ARS' and cuerpo['installments'] == [1]
    assert cuerpo['site'] == '0001' and cuerpo['establishment_number'] == 123
    assert pago.codigo in cuerpo['payment_description']
    assert cuerpo['notifications_url'].endswith(f'/pagos/aviso/taller-a/{pago.codigo}/')


def t_A():
    from talleres.models import Taller
    return Taller.objects.get(slug='taller-a')


def pago_payway(id_, monto, cuando, estado='approved', escala=10):
    """Un pago como los que devuelve Payway: `amount` ×10 (Sandbox) y la hora argentina con una Z de más."""
    from zoneinfo import ZoneInfo
    hora = cuando.astimezone(ZoneInfo('America/Argentina/Buenos_Aires')).strftime('%Y-%m-%dT%H:%MZ')
    return {'id': id_, 'site_transaction_id': f'CH{id_}', 'status': estado, 'amount': int(monto * escala),
            'date': hora, 'card_data': {'card_number': '450799'}}


def test_payway_reconoce_el_pago_por_monto_y_fecha(payway):
    pago = pago_pendiente(t_A(), None)
    ahora = timezone.now()
    payway.pagos['1'] = pago_payway(1, pago.monto_ars + 3, ahora)                  # otro monto
    payway.pagos['2'] = pago_payway(2, pago.monto_ars, ahora - timedelta(hours=1))  # antes del link
    with con_taller(t_A()):
        assert confirmar(pago) == 'pendiente'
        payway.pagos['3'] = pago_payway(3, pago.monto_ars, ahora)                  # este
        assert confirmar(Pago.objects.get(pk=pago.pk), aviso={}) == 'aprobado'
        p = Pago.objects.get(pk=pago.pk)
        assert p.id_externo == '3' and p.datos['site_transaction_id'] == 'CH3' and 'card_data' not in p.datos
        assert suscripcion_de(t_A()).pagado_hasta == p.hasta


def test_payway_acepta_amount_en_centavos(payway):
    pago = pago_pendiente(t_A(), None)
    payway.pagos['9'] = pago_payway(9, pago.monto_ars, timezone.now(), escala=100)
    with con_taller(t_A()):
        assert confirmar(pago) == 'aprobado'


def test_payway_con_dos_pagos_iguales_no_elige(payway):
    pago = pago_pendiente(t_A(), None)
    ahora = timezone.now()
    payway.pagos['1'] = pago_payway(1, pago.monto_ars, ahora)
    payway.pagos['2'] = pago_payway(2, pago.monto_ars, ahora)
    with con_taller(t_A()):
        assert confirmar(pago) == 'pendiente'
        assert Pago.objects.get(pk=pago.pk).datos['coinciden'] == ['1', '2']


def test_payway_un_pago_aprueba_un_solo_link(payway):
    primero = pago_pendiente(t_A(), None)
    payway.pagos['7'] = pago_payway(7, primero.monto_ars, timezone.now())
    with con_taller(t_A()):
        assert confirmar(primero) == 'aprobado'
        otro = pago_pendiente(t_A(), None)
        Pago.objects.filter(pk=otro.pk).update(monto_ars=primero.monto_ars)        # mismo monto a propósito
        assert confirmar(Pago.objects.get(pk=otro.pk), aviso={'payment_id': '7'}) == 'pendiente'


def test_payway_aviso_con_un_pago_ajeno_no_aprueba(payway):
    pago = pago_pendiente(t_A(), None)
    payway.pagos['5'] = pago_payway(5, pago.monto_ars + 500, timezone.now())       # existe, pero es de otro monto
    with con_taller(t_A()):
        assert confirmar(pago, aviso={'id': '5'}) == 'pendiente'
        assert 'revisar a mano' in Pago.objects.get(pk=pago.pk).nota


def test_payway_sin_claves_avisa(cobro, settings, cliente_de):
    configurar(pasarela='payway', sitio='1', clave_publica='x')
    settings.PAYWAY_CLAVE_PRIVADA = ''
    r = cliente_de(cobro.dueno_a).post('/taller-a/suscripcion/pagar/', {'plan': plan_db('pro').pk,
                                                                        'periodo': 'mensual'}, follow=True)
    assert 'Falta la clave privada de Payway' in r.content.decode()


def test_cotizacion_del_bcra(db, monkeypatch):
    def get(url, params=None, timeout=None):
        assert url.endswith('/monetarias/4')
        return Respuesta(200, {'results': [{'idVariable': 4, 'detalle': [
            {'fecha': '2026-11-04', 'valor': 1571.4}, {'fecha': '2026-11-03', 'valor': 1572.65}]}]})
    monkeypatch.setattr(cotizacion.requests, 'get', get)
    c = cotizacion.actualizar(HOY)
    assert c.fecha == date(2026, 11, 4) and c.ars_por_usd == Decimal('1571.40') and c.fuente == 'bcra'


def test_cotizacion_sin_bcra_sigue_la_ultima(db, monkeypatch):
    def get(*a, **k):
        raise ConnectionError('sin red')
    monkeypatch.setattr(cotizacion.requests, 'get', get)
    assert cotizacion.actualizar(HOY) is None


# ---------------------------------------------------------------- link del cliente según el plan y el estado

def test_link_del_cliente_segun_el_plan(cobro, client):
    from tests.app.test_visor import config_de, link_de, proyecto_listo
    cobro.A.color = '#2F6F5E'
    cobro.A.save()
    p = proyecto_listo(cobro.A)
    link = link_de(cobro.A, p)
    hoy = timezone.localdate()
    guardar(cobro.A, plan=plan_db('taller'), prueba_hasta=hoy - timedelta(days=60), pagado_hasta=hoy + timedelta(days=9))
    config = config_de(client.get(f'/c/{link.codigo}/'))
    assert config['ar'] is False and config['marca'] == {'nombre': 'Taller A', 'color': None, 'logo': None}
    assert client.get(f'/c/{link.codigo}/data/clientes/{p.codigo_cliente}/todo.glb').status_code == 404
    guardar(cobro.A, plan=plan_db('fabrica'))
    config = config_de(client.get(f'/c/{link.codigo}/'))
    assert config['ar'] is True and config['marca']['color'] == '#2F6F5E'
    assert client.get(f'/c/{link.codigo}/data/clientes/{p.codigo_cliente}/todo.glb').status_code == 200


def test_link_del_cliente_no_anda_con_la_cuenta_suspendida(cobro, client):
    from tests.app.test_visor import link_de, proyecto_listo
    link = link_de(cobro.A, proyecto_listo(cobro.A))
    hoy = timezone.localdate()
    guardar(cobro.A, prueba_hasta=hoy - timedelta(days=200), pagado_hasta=hoy - timedelta(days=95))
    assert client.get(f'/c/{link.codigo}/').status_code == 404
    guardar(cobro.A, pagado_hasta=hoy - timedelta(days=30))          # solo lectura: el cliente sigue viendo
    assert client.get(f'/c/{link.codigo}/').status_code == 200


def test_visor_sin_produccion_en_el_plan(cobro, cliente_de):
    from tests.app.test_visor import config_de
    hoy = timezone.localdate()
    guardar(cobro.A, plan=plan_db('taller'), prueba_hasta=hoy - timedelta(days=60), pagado_hasta=hoy + timedelta(days=9))
    c = cliente_de(cobro.dueno_a)
    assert config_de(c.get('/taller-a/visor/'))['avance'] is None
    r = c.get('/taller-a/visor/api/avance?p=1')
    assert r.status_code == 403 and 'Producción' in r.json()['error']
    menu = c.get('/taller-a/').content.decode()
    assert 'Mi puesto' not in menu and 'Suscripción' in menu


def test_administracion_de_la_configuracion_del_cobro(db, client, django_user_model):
    admin = django_user_model.objects.create_superuser('martin@servicio.com', 'clave-larga-de-prueba')
    client.force_login(admin)
    r = client.get('/admin/suscripciones/cobro/')
    assert r.status_code == 302 and r.url.endswith('/admin/suscripciones/cobro/1/change/')
    r = client.get(r.url)
    html = r.content.decode()
    assert r.status_code == 200 and 'clave pública' in html.lower() and 'PAYWAY_CLAVE_PRIVADA' in html
    assert 'name="clave_privada"' not in html
    r = client.post('/admin/suscripciones/cobro/1/change/', {'activo': 'on', 'pasarela': 'payway', 'ambiente': 'sandbox',
                                                             'sitio': '92003323', 'establecimiento': '',
                                                             'cuit': '20-1', 'clave_publica': 'x'})
    assert r.status_code == 200 and 'sin guiones' in r.content.decode()          # CUIT mal: no guarda
    r = client.post('/admin/suscripciones/cobro/1/change/', {'activo': 'on', 'pasarela': 'payway', 'ambiente': 'sandbox',
                                                             'sitio': '92003323', 'establecimiento': '',
                                                             'cuit': '20111111112', 'clave_publica': 'x'})
    assert r.status_code == 302 and config_cobro().activo and config_cobro().sitio == '92003323'


def test_si_payway_no_arma_el_link_no_queda_un_pago_suelto(payway, monkeypatch):
    import suscripciones.pasarelas as p
    monkeypatch.setattr(p.requests, 'post', lambda *a, **k: Respuesta(403, {'message': 'Forbidden'}))
    with pytest.raises(p.ErrorPayway):
        pago_pendiente(t_A(), None)
    with con_taller(t_A()):
        assert not Pago.objects.exists()


def test_payway_recorre_las_paginas_y_saltea_las_viejas(payway, monkeypatch):
    import suscripciones.pasarelas as p
    monkeypatch.setattr(p.Payway, 'POR_PAGINA', 2)
    hace_mucho = timezone.now() - timedelta(days=30)
    for i in range(1, 6):                                                          # 5 pagos viejos: 2 páginas llenas
        payway.pagos[str(i)] = pago_payway(i, 1000 + i, hace_mucho)
    pago = pago_pendiente(t_A(), None)
    payway.pagos['9'] = pago_payway(9, pago.monto_ars, timezone.now())            # en la 3ª página
    with con_taller(t_A()):
        assert confirmar(pago) == 'aprobado'
    from django.core.cache import cache
    assert cache.get('payway-desde-sandbox-0001') == 4                              # la próxima arranca en la 3ª
    otro = pago_pendiente(t_A(), None)
    payway.pagos['10'] = pago_payway(10, otro.monto_ars, timezone.now())
    payway.pedidos.clear()
    with con_taller(t_A()):
        assert confirmar(otro) == 'aprobado'
    assert [x[2]['offset'] for x in payway.pedidos if x[0] == 'get'] == [4, 6]       # no releyó las viejas
