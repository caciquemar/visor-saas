"""Lo que la suscripción hace con la base: crearla, actualizar su estado, cobrar y confirmar pagos. Las reglas están
en `estados.py`; acá todo corre dentro del taller del contexto (pedido, tarea o administración con con_taller)."""
import logging
import secrets
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from talleres.separacion import con_taller

from . import estados
from .config import cobro_activo
from .models import Cotizacion, Pago, Plan, Suscripcion

log = logging.getLogger('visor.suscripciones')

LINK_VALE_DIAS = 2          # un pago pendiente más viejo que esto, si la pasarela no lo tiene aprobado, vence


def hoy():
    return timezone.localdate()


def plan_de_prueba():
    return Plan.objects.filter(clave=estados.PLAN_DE_PRUEBA).first()


def crear_suscripcion(taller):
    with con_taller(taller):
        if Suscripcion.objects.exists():
            return Suscripcion.objects.get()
        plan = plan_de_prueba() or Plan.objects.order_by('-orden').first()
        return Suscripcion.objects.create(plan=plan, prueba_hasta=hoy() + timedelta(days=estados.DIAS_DE_PRUEBA - 1),
                                          estado=estados.PRUEBA, estado_desde=hoy())


def suscripcion_de(taller):
    """La del taller del contexto (la crea si falta, por ejemplo un taller de antes de la ficha 08)."""
    s = Suscripcion.objects.select_related('plan', 'plan_proximo').first()
    return s or crear_suscripcion(taller)


def plan_vigente(s, dia=None):
    return estados.plan_vigente(s, dia or hoy(), plan_de_prueba())


def estado_de(s, dia=None):
    return estados.estado(s, dia or hoy())


def actualizar(s, dia=None):
    """Guarda el estado del día (y el cambio de plan que toque). Devuelve True si cambió algo."""
    dia = dia or hoy()
    cambio = estados.cambiar_plan_si_toca(s, dia)
    nuevo = estados.estado(s, dia)
    if nuevo != s.estado:
        s.estado, s.estado_desde, cambio = nuevo, dia, True
    if cambio:
        s.save()
    return cambio


# ---------------------------------------------------------------- precios

def cotizacion_vigente():
    return Cotizacion.objects.order_by('-fecha', '-creada').first()


def cotizar(s, plan, periodo, dia=None):
    """La cotización de `estados.cotizar` en pesos (None si todavía no hay cotización del dólar)."""
    c = estados.cotizar(s, plan, periodo, dia or hoy())
    dolar = cotizacion_vigente()
    if dolar is None:
        return None
    return dict(c, cotizacion=dolar.ars_por_usd, ars=estados.redondear_pesos(c['usd'] * dolar.ars_por_usd))


def opciones(s, dia=None):
    """Para la pantalla: por cada plan a la venta, el precio de cada período."""
    salida = []
    for plan in Plan.objects.filter(a_la_venta=True):
        salida.append({'plan': plan, 'periodos': [dict(cotizar(s, plan, p, dia) or {}, periodo=p)
                                                   for p in estados.PERIODOS]})
    return salida


# ---------------------------------------------------------------- pagos

def nuevo_pago(s, plan, periodo, usuario, urls):
    """Crea el pago pendiente y el link en la pasarela. `urls(pago)` da {'volver', 'aviso'} absolutas."""
    from .pasarelas import pasarela
    c = cotizar(s, plan, periodo)
    if c is None:
        raise ValueError('Todavía no hay cotización del dólar.')
    p = pasarela()
    monto = c['ars']
    if p.monto_unico:       # unos pesos menos que el precio: así el pago de Payway se reconoce por el monto
        monto -= secrets.randbelow(99) + 1
    pago = Pago.objects.create(suscripcion=s, plan=plan, periodo=periodo, meses=c['meses'], monto_usd=c['usd'],
                               cotizacion=c['cotizacion'], monto_ars=monto, pasarela=p.nombre, creado_por=usuario,
                               desde=c['desde'], hasta=c['hasta'])
    try:
        pago.link, pago.id_externo = p.crear_link(pago, urls(pago))
    except Exception:
        pago.delete()               # sin link no hay pago: no queda un "pendiente" suelto
        raise
    pago.save(update_fields=['link', 'id_externo'])
    return pago


def confirmar(pago, aviso=None):
    """Pregunta a la pasarela cómo está el pago (el aviso solo dice que algo cambió; no se le cree). Aprobado: corre
    lo pagado. Devuelve el estado del pago."""
    from .pasarelas import pasarela_de
    if pago.estado != Pago.Estado.PENDIENTE:
        return pago.estado
    r = pasarela_de(pago.pasarela).consultar(pago, aviso)
    if r.datos:
        pago.datos = {**r.datos, **({'simulada': pago.datos['simulada']} if 'simulada' in (pago.datos or {}) else {})}
    if r.estado == Pago.Estado.APROBADO:
        problema = problema_con(pago, r)
        if problema:
            log.error('Pago %s no se aprueba solo: %s', pago.codigo, problema)
            pago.nota = problema[:200]
            pago.save()
            return pago.estado
    if r.id_externo and not pago.id_externo:
        pago.id_externo = r.id_externo
        try:
            with transaction.atomic():
                pago.save(update_fields=['id_externo', 'datos'])
        except IntegrityError:
            log.error('Pago %s: el pago %s de la pasarela ya aprobó otro pago', pago.codigo, r.id_externo)
            return Pago.Estado.PENDIENTE
    if r.estado == Pago.Estado.APROBADO:
        return aprobar(pago).estado
    elif r.estado == Pago.Estado.RECHAZADO and es_este(pago, r):
        pago.estado, pago.resuelto = Pago.Estado.RECHAZADO, timezone.now()
        pago.save()
    else:
        pago.save()
    return pago.estado


def problema_con(pago, r):
    """Por qué un pago que la pasarela da por aprobado no se aprueba solo (el id llegó en un aviso o en la vuelta,
    que cualquiera puede mandar): monto distinto o que no sea el pago de este link. Queda para revisar a mano."""
    if not es_este(pago, r):
        return 'No se pudo comprobar que el pago sea el de este link (monto o fecha): revisar a mano en Payway'
    if r.monto is None or abs(r.monto - pago.monto_ars) > 1:
        return f'Monto distinto en la pasarela: {r.monto} (se pidió {pago.monto_ars})'
    return ''


def es_este(pago, r):
    """La pasarela comprobó que el pago es el de este link: la simulada, por el código; Payway, por el monto único y la
    fecha (pasarelas.Payway.coincide), porque su pago no trae nada nuestro."""
    return r.verificado


def aprobar(pago, nota=''):
    """Pago aprobado (por la pasarela o a mano en la administración, por ejemplo una transferencia)."""
    with transaction.atomic():
        s = Suscripcion.objects.select_for_update().get(pk=pago.suscripcion_id)
        pago = Pago.objects.select_for_update().get(pk=pago.pk)
        if pago.estado == Pago.Estado.APROBADO:
            return pago
        estados.aplicar_pago(s, pago, hoy())
        pago.estado, pago.resuelto = Pago.Estado.APROBADO, timezone.now()
        if nota:
            pago.nota = nota
        pago.save()
        s.save()
        actualizar(s)
    log.info('Pago %s aprobado: %s hasta %s', pago.codigo, pago.plan, s.pagado_hasta)
    return pago


def revisar_pendientes(s, dia=None):
    """Lo que no llegó por aviso: consulta los pendientes y vence los viejos que siguen sin pagar."""
    limite = timezone.now() - timedelta(days=LINK_VALE_DIAS)
    for pago in Pago.objects.filter(suscripcion=s, estado=Pago.Estado.PENDIENTE):
        try:
            estado = confirmar(pago)
        except Exception:
            log.exception('No se pudo consultar el pago %s', pago.codigo)
            continue
        if estado == Pago.Estado.PENDIENTE and pago.creado < limite:
            pago.estado, pago.resuelto = Pago.Estado.VENCIDO, timezone.now()
            pago.save(update_fields=['estado', 'resuelto'])


def revisar_taller(taller, dia=None):
    """La revisión diaria de un taller: pagos pendientes, estado y avisos por mail."""
    from .avisos import mandar_avisos
    with con_taller(taller):
        s = suscripcion_de(taller)
        revisar_pendientes(s, dia)
        s.refresh_from_db()
        actualizar(s, dia)
        if cobro_activo():
            mandar_avisos(s, dia or hoy())
