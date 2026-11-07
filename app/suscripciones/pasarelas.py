"""Por dónde se cobra. Cada pasarela hace dos cosas: armar el link de pago y decir cómo está un pago. Para sumar otra
(por ejemplo una para cobrar en el exterior) alcanza con otra clase y su nombre en PASARELAS.

- `simulada`: para la PC y las pruebas. El link lleva a una página de la app con "Aprobar" y "Rechazar".
- `payway`: Payway Argentina, Link Checkout (el taller paga en la página de Payway; acá no pasa la tarjeta).
"""
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.urls import reverse
from django.utils.dateparse import parse_datetime

from .models import Pago

log = logging.getLogger('visor.suscripciones')
HORA_ARGENTINA = ZoneInfo('America/Argentina/Buenos_Aires')


@dataclass
class Resultado:
    estado: str = Pago.Estado.PENDIENTE
    monto: Decimal | None = None
    id_externo: str = ''
    datos: dict = field(default_factory=dict)
    verificado: bool = False        # la pasarela comprobó que este pago es el del link (no solo que existe)


class Simulada:
    nombre = 'simulada'
    monto_unico = False

    def crear_link(self, pago, urls):
        ruta = reverse('pagos:simulada', args=[pago.taller.slug, pago.codigo])
        return settings.URL_APP.rstrip('/') + ruta, ''

    def consultar(self, pago, aviso=None):
        elegido = (pago.datos or {}).get('simulada')
        if elegido in (Pago.Estado.APROBADO, Pago.Estado.RECHAZADO):
            return Resultado(elegido, pago.monto_ars, f'sim-{pago.pk}', pago.datos, verificado=True)
        return Resultado()


class ErrorPayway(RuntimeError):
    pass


class Payway:
    """API de Payway Venta Online. Link Checkout: POST <checkout>/link (encabezado `apikey` con la clave privada)
    devuelve `payment_link`. Los pagos se leen con GET <api>/payments.

    Probado en Sandbox (2026-11-07): la vuelta a `success_url` no trae parámetros y el pago no trae nuestra
    descripción ni el código del link. Por eso cada link tiene un **monto único** (unos pesos menos que el precio,
    `servicio.nuevo_pago`) y el pago se reconoce buscando en Payway uno aprobado de ese monto, del sitio, hecho
    después de crear el link y antes de que venza. Si hay más de uno, no se elige: queda para aprobar a mano.
    `amount` vino ×10 (299000 por $ 29.900), no en centavos como dicen los SDK: se aceptan las dos escalas."""
    nombre = 'payway'
    URLS = {
        'sandbox': ('https://developers.decidir.com/api/v2/',
                    'https://developers.decidir.com/api/v1/checkout-payment-button/'),   # probado en Sandbox
        'produccion': ('https://ventasonline.payway.com.ar/api/v2/',
                       'https://ventasonline.payway.com.ar/api/v1/checkout-payment-button/'),
    }
    ESTADOS = {'approved': Pago.Estado.APROBADO, 'accredited': Pago.Estado.APROBADO,
               'rejected': Pago.Estado.RECHAZADO, 'annulled': Pago.Estado.RECHAZADO,
               'group_rejected': Pago.Estado.RECHAZADO}
    SEGUNDOS = 20
    monto_unico = True
    ESCALAS = (10, 100)             # amount = pesos × 10 (visto en Sandbox) o × 100 (centavos, según los SDK)
    VENTANA = timedelta(days=2)     # un pago cuenta para un link si se hizo hasta 2 días después de crearlo
    TOLERANCIA = timedelta(minutes=5)   # relojes y la hora sin segundos de Payway

    def __init__(self):
        from .config import cobro
        self.cfg = cobro()
        api, checkout = self.URLS[self.cfg.ambiente]
        self.api = settings.PAYWAY_URL_API or api
        self.checkout = settings.PAYWAY_URL_CHECKOUT or checkout
        if not settings.PAYWAY_CLAVE_PRIVADA:
            raise ErrorPayway('Falta la clave privada de Payway en el .env del servidor (PAYWAY_CLAVE_PRIVADA).')
        if not (self.cfg.clave_publica and self.cfg.sitio):
            raise ErrorPayway('Faltan la clave pública o el número de sitio de Payway en la administración '
                              '(Configuración del cobro).')

    def _encabezados(self):
        return {'apikey': settings.PAYWAY_CLAVE_PRIVADA, 'Content-Type': 'application/json',
                'Cache-Control': 'no-cache'}

    def crear_link(self, pago, urls):
        cuerpo = {
            'origin_platform': 'visor',
            'payment_description': f'{pago.plan} {pago.get_periodo_display().lower()} ({pago.codigo})',
            # sin 'products': Payway no acepta productos y descripción juntos (la descripción lleva el código)
            'total_price': float(pago.monto_ars),
            'site': self.cfg.sitio,
            'success_url': urls['volver'],          # Payway no acepta success_url y redirect_url juntas
            'cancel_url': urls['volver'],
            'notifications_url': urls['aviso'],
            'template_id': 1,
            'installments': [1],
            'plan_gobierno': False,
            'public_apikey': self.cfg.clave_publica,
            'currency': 'ARS',
        }
        if self.cfg.establecimiento:
            cuerpo['establishment_number'] = int(self.cfg.establecimiento)
        if self.cfg.cuit:
            cuerpo['cuit'] = self.cfg.cuit
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

    @classmethod
    def coincide(cls, pago, datos):
        """El pago de Payway es por el monto de este link (en alguna de las escalas) y se hizo en su ventana."""
        amount = datos.get('amount')
        if amount is None or not any(Decimal(str(amount)) == pago.monto_ars * e for e in cls.ESCALAS):
            return False
        fecha = cls.fecha_de(datos)
        if fecha is None:
            return False
        return pago.creado - cls.TOLERANCIA <= fecha <= pago.creado + cls.VENTANA

    @staticmethod
    def fecha_de(datos):
        """`date` de Payway ("2026-11-07T10:29Z"): dice Z pero es hora argentina (visto en Sandbox: el comprobante
        decía 10:29 y el link se creó 10:27 de la Argentina, 13:27 UTC)."""
        fecha = parse_datetime(str(datos.get('date') or '').rstrip('Z'))
        if fecha is None:
            return None
        return fecha.replace(tzinfo=HORA_ARGENTINA)

    def resultado(self, pago, datos):
        datos = {k: v for k, v in datos.items() if k != 'card_data'}       # nada de la tarjeta
        estado = self.ESTADOS.get(str(datos.get('status', '')).lower(), Pago.Estado.PENDIENTE)
        verificado = self.coincide(pago, datos)
        return Resultado(estado, pago.monto_ars if verificado else None, str(datos.get('id', '')), datos, verificado)

    def buscar(self, pago):
        """Los pagos aprobados del sitio que coinciden con el link (los más nuevos primero; Payway pagina)."""
        r = requests.get(f'{self.api}payments', params={'pageSize': 50, 'siteId': self.cfg.sitio},
                         headers=self._encabezados(), timeout=self.SEGUNDOS)
        r.raise_for_status()
        return [d for d in r.json().get('results', [])
                if str(d.get('status', '')).lower() in ('approved', 'accredited') and self.coincide(pago, d)]

    def consultar(self, pago, aviso=None):
        id_pago = pago.id_externo or self.id_en(aviso)
        if id_pago:
            r = requests.get(f'{self.api}payments/{id_pago}', headers=self._encabezados(), timeout=self.SEGUNDOS)
            if r.status_code == 404:
                return Resultado()
            r.raise_for_status()
            return self.resultado(pago, r.json())
        encontrados = self.buscar(pago)
        if len(encontrados) == 1:
            return self.resultado(pago, encontrados[0])
        if len(encontrados) > 1:
            log.warning('Pago %s: %s pagos de Payway coinciden; queda para aprobar a mano', pago.codigo,
                        len(encontrados))
            return Resultado(datos={'coinciden': [str(d.get('id')) for d in encontrados]})
        return Resultado()


PASARELAS = {'simulada': Simulada, 'payway': Payway}


def pasarela_de(nombre):
    return PASARELAS[nombre]()


def pasarela():
    from .config import nombre_de_pasarela
    return pasarela_de(nombre_de_pasarela())
