"""Por dónde se cobra. Cada pasarela hace dos cosas: armar el link de pago y decir cómo está un pago. Para sumar otra
(por ejemplo una para cobrar en el exterior) alcanza con otra clase y su nombre en PASARELAS.

- `simulada`: para la PC y las pruebas. El link lleva a una página de la app con "Aprobar" y "Rechazar".
- `payway`: Payway Argentina, Link Checkout (el taller paga en la página de Payway; acá no pasa la tarjeta).
"""
import logging
from dataclasses import dataclass, field
from decimal import Decimal

import requests
from django.conf import settings
from django.urls import reverse

from .models import Pago

log = logging.getLogger('visor.suscripciones')


@dataclass
class Resultado:
    estado: str = Pago.Estado.PENDIENTE
    monto: Decimal | None = None
    id_externo: str = ''
    datos: dict = field(default_factory=dict)


class Simulada:
    nombre = 'simulada'

    def crear_link(self, pago, urls):
        ruta = reverse('pagos:simulada', args=[pago.taller.slug, pago.codigo])
        return settings.URL_APP.rstrip('/') + ruta, ''

    def consultar(self, pago, aviso=None):
        elegido = (pago.datos or {}).get('simulada')
        if elegido in (Pago.Estado.APROBADO, Pago.Estado.RECHAZADO):
            return Resultado(elegido, pago.monto_ars, f'sim-{pago.pk}', pago.datos)
        return Resultado()


class ErrorPayway(RuntimeError):
    pass


class Payway:
    """API de Payway Venta Online. Link Checkout: POST <checkout>/link (encabezado `apikey` con la clave privada)
    devuelve `payment_link`. El estado se consulta con GET <api>/payments/<id>.

    Lo que la documentación pública no dice, y se confirma en el ambiente de prueba (pedido a soporte de Payway):
    qué manda el aviso a `notifications_url` y con qué id buscar el pago. Por eso el aviso se guarda entero y se
    busca un id de pago en él; sin id, el pago queda pendiente y se aprueba a mano en la administración."""
    nombre = 'payway'
    URLS = {
        'sandbox': ('https://developers.decidir.com/api/v2/', 'https://developers.decidir.com/api/checkout/'),
        'produccion': ('https://ventasonline.payway.com.ar/api/v2/',
                       'https://ventasonline.payway.com.ar/api/v1/checkout-payment-button/'),
    }
    ESTADOS = {'approved': Pago.Estado.APROBADO, 'accredited': Pago.Estado.APROBADO,
               'rejected': Pago.Estado.RECHAZADO, 'annulled': Pago.Estado.RECHAZADO,
               'group_rejected': Pago.Estado.RECHAZADO}
    SEGUNDOS = 20

    def __init__(self):
        api, checkout = self.URLS[settings.PAYWAY_AMBIENTE]
        self.api = settings.PAYWAY_URL_API or api
        self.checkout = settings.PAYWAY_URL_CHECKOUT or checkout
        if not (settings.PAYWAY_CLAVE_PRIVADA and settings.PAYWAY_CLAVE_PUBLICA and settings.PAYWAY_SITIO):
            raise ErrorPayway('Faltan las claves de Payway en el .env (PAYWAY_CLAVE_PRIVADA, PAYWAY_CLAVE_PUBLICA, '
                              'PAYWAY_SITIO).')

    def _encabezados(self):
        return {'apikey': settings.PAYWAY_CLAVE_PRIVADA, 'Content-Type': 'application/json',
                'Cache-Control': 'no-cache'}

    def crear_link(self, pago, urls):
        cuerpo = {
            'origin_platform': 'visor',
            'payment_description': f'{pago.plan} {pago.get_periodo_display().lower()} ({pago.codigo})',
            'products': [{'id': pago.pk, 'value': float(pago.monto_ars), 'quantity': 1,
                          'description': f'Plan {pago.plan}, {pago.get_periodo_display().lower()}'}],
            'total_price': float(pago.monto_ars),
            'site': settings.PAYWAY_SITIO,
            'success_url': urls['volver'],
            'redirect_url': urls['volver'],
            'cancel_url': urls['volver'],
            'notifications_url': urls['aviso'],
            'template_id': 1,
            'installments': [1],
            'plan_gobierno': False,
            'public_apikey': settings.PAYWAY_CLAVE_PUBLICA,
            'currency': 'ARS',
        }
        if settings.PAYWAY_ESTABLECIMIENTO:
            cuerpo['establishment_number'] = int(settings.PAYWAY_ESTABLECIMIENTO)
        if settings.PAYWAY_CUIT:
            cuerpo['cuit'] = settings.PAYWAY_CUIT
        r = requests.post(self.checkout + 'link', json=cuerpo, headers=self._encabezados(), timeout=self.SEGUNDOS)
        if r.status_code >= 400:
            log.error('Payway no armó el link (%s): %s', r.status_code, r.text[:500])
            raise ErrorPayway('Payway no pudo armar el link de pago. Probá de nuevo en un rato.')
        link = r.json().get('payment_link')
        if not link:
            raise ErrorPayway('Payway no devolvió el link de pago.')
        return link, ''

    @staticmethod
    def id_en(aviso):
        """El id del pago en un aviso o en los parámetros de la vuelta (el formato exacto se confirma en Sandbox)."""
        for clave in ('payment_id', 'paymentId', 'id_pago', 'id'):
            valor = (aviso or {}).get(clave)
            if valor not in (None, '') and str(valor).isdigit():
                return str(valor)
        datos = (aviso or {}).get('data')
        return Payway.id_en(datos) if isinstance(datos, dict) else ''

    def consultar(self, pago, aviso=None):
        id_pago = pago.id_externo or self.id_en(aviso)
        if not id_pago:
            return Resultado()
        r = requests.get(f'{self.api}payments/{id_pago}', headers=self._encabezados(), timeout=self.SEGUNDOS)
        if r.status_code == 404:
            return Resultado()
        r.raise_for_status()
        datos = r.json()
        datos.pop('card_data', None)            # no se guarda nada de la tarjeta
        estado = self.ESTADOS.get(str(datos.get('status', '')).lower(), Pago.Estado.PENDIENTE)
        # En la API de pagos `amount` va en centavos (README de los SDK de Payway). Si no fuera así, el monto no
        # coincide y el pago no se aprueba solo (servicio.confirmar): nunca se aprueba de más.
        monto = datos.get('amount')
        monto = Decimal(str(monto)) / 100 if monto is not None else None
        return Resultado(estado, monto, str(id_pago), datos)


PASARELAS = {'simulada': Simulada, 'payway': Payway}


def pasarela_de(nombre):
    return PASARELAS[nombre]()


def pasarela():
    return pasarela_de(settings.PASARELA)
