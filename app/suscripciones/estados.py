"""Las reglas de la suscripción, en un solo lugar y sin tocar la base: qué estado tiene un taller en un día, qué
plan rige, cuánto sale cada período y qué hace un pago aprobado. Las pruebas pasan `hoy` a mano.

Estados (días desde que se terminó lo pagado, la prueba o el "sin cobro"):
    prueba        30 días con el plan Pro (o el plan elegido, si es mejor)
    activa        pagado (o sin cobro) hasta una fecha
    vencida       días 1 a GRACIA: todo anda, con aviso. Si nunca pagó (prueba vencida), no hay gracia.
    solo_lectura  hasta SUSPENDER: ve todo, no cambia nada
    suspendida    hasta BORRAR: solo entra quien maneja la suscripción, a pagar; el link del cliente no anda
    para_borrar   desde BORRAR: se le avisó; el borrado lo confirma Martín en la administración
"""
import calendar
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

DIAS_DE_PRUEBA = 30
GRACIA = 7
SUSPENDER = 90
BORRAR = 180
AVISOS_DE_BORRADO = (30, 7)            # días antes de BORRAR
AVISOS_DE_VENCIMIENTO = (7, 1)         # días antes de que se termine lo pagado o la prueba

PRUEBA, ACTIVA, VENCIDA, SOLO_LECTURA, SUSPENDIDA, PARA_BORRAR = (
    'prueba', 'activa', 'vencida', 'solo_lectura', 'suspendida', 'para_borrar')
NOMBRES = {PRUEBA: 'En prueba', ACTIVA: 'Activa', VENCIDA: 'Vencida', SOLO_LECTURA: 'Solo lectura',
           SUSPENDIDA: 'Suspendida', PARA_BORRAR: 'Para borrar'}
CON_TODO = (PRUEBA, ACTIVA, VENCIDA)   # estados en que el taller usa todo lo de su plan

# período: (meses de servicio, meses que se pagan)
PERIODOS = {'mensual': (1, Decimal('1')), 'semestral': (6, Decimal('5.5')), 'anual': (12, Decimal('10'))}
PLAN_DE_PRUEBA = 'pro'


def sumar_meses(dia, meses):
    """El mismo día `meses` después (o el último del mes, si no existe: 31/1 + 1 = 28/2)."""
    m = dia.month - 1 + meses
    anio, mes = dia.year + m // 12, m % 12 + 1
    return date(anio, mes, min(dia.day, calendar.monthrange(anio, mes)[1]))


def cubierto_hasta(s):
    """El último día con servicio: lo pagado, la prueba o el sin cobro, lo que llegue más lejos."""
    return max(d for d in (s.prueba_hasta, s.pagado_hasta, s.sin_cobro_hasta) if d is not None)


def pago_alguna_vez(s):
    return s.pagado_hasta is not None or s.sin_cobro_hasta is not None


def estado(s, hoy):
    hasta = cubierto_hasta(s)
    if hoy <= hasta:
        # Quien paga durante la prueba la termina igual: su período empieza después (ver `cotizar`).
        sin_cobro = s.sin_cobro_hasta and hoy <= s.sin_cobro_hasta
        return PRUEBA if hoy <= s.prueba_hasta and not sin_cobro else ACTIVA
    dias = (hoy - hasta).days
    if dias <= GRACIA and pago_alguna_vez(s):
        return VENCIDA
    if dias <= SUSPENDER:
        return SOLO_LECTURA
    if dias <= BORRAR:
        return SUSPENDIDA
    return PARA_BORRAR


def en_prueba(s, hoy):
    return estado(s, hoy) == PRUEBA


def plan_vigente(s, hoy, plan_de_prueba):
    """En prueba rige el Pro, salvo que ya haya elegido uno mejor."""
    if en_prueba(s, hoy) and plan_de_prueba is not None and plan_de_prueba.orden > s.plan.orden:
        return plan_de_prueba
    return s.plan


def redondear_pesos(monto):
    """A la centena: $ 61.234 -> $ 61.200."""
    return (Decimal(monto) / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * 100


def precio_usd(plan, periodo):
    return (plan.precio_usd * PERIODOS[periodo][1]).quantize(Decimal('0.01'))


def dias_pagos_que_quedan(s, hoy):
    """Días de lo ya pagado que faltan usar (para el cambio de plan)."""
    if s.pagado_hasta is None or s.pagado_hasta < hoy:
        return 0
    return (s.pagado_hasta - hoy).days + 1


def diferencia_usd(s, nuevo, hoy):
    """Lo que cuesta pasar ya a un plan mejor por lo que queda pagado: la diferencia por mes, proporcional a los días
    (30 por mes). Cero si no hay nada pagado o el plan no es mejor."""
    dias = dias_pagos_que_quedan(s, hoy)
    if dias == 0 or nuevo.orden <= s.plan.orden:
        return Decimal('0')
    return ((nuevo.precio_usd - s.plan.precio_usd) * dias / 30).quantize(Decimal('0.01'))


def cotizar(s, plan, periodo, hoy):
    """Qué se cobra por pagar `periodo` del `plan` hoy: {'usd', 'meses', 'diferencia_usd', 'desde', 'hasta',
    'inmediato'}. Un plan mejor con días pagados suma la diferencia y cambia ya; uno peor empieza cuando se termina
    lo pagado."""
    meses = PERIODOS[periodo][0]
    usd = precio_usd(plan, periodo)
    dif = diferencia_usd(s, plan, hoy)
    pagado = s.pagado_hasta if s.pagado_hasta and s.pagado_hasta >= hoy else None
    # En prueba, el período empieza cuando se termina la prueba (no se pierden los días de regalo).
    base = max(d for d in (pagado, s.prueba_hasta if en_prueba(s, hoy) else None, hoy - timedelta(days=1))
               if d is not None)
    desde = base + timedelta(days=1)
    return {'usd': usd + dif, 'meses': meses, 'diferencia_usd': dif, 'desde': desde,
            'hasta': sumar_meses(desde, meses) - timedelta(days=1),
            'inmediato': pagado is None or plan.orden >= s.plan.orden}


def aplicar_pago(s, pago, hoy):
    """Un pago aprobado: corre lo pagado y cambia el plan (ya o desde el próximo período). Modifica `s` y `pago`
    sin guardar. Si el pago llega tarde (el link se pagó días después), el período se vuelve a calcular desde hoy."""
    if pago.periodo == 'diferencia':
        s.plan, s.plan_proximo, s.cambio_de_plan = pago.plan, None, None
        return
    c = cotizar(s, pago.plan, pago.periodo, hoy)
    pago.desde, pago.hasta = c['desde'], c['hasta']
    if c['inmediato']:
        s.plan, s.plan_proximo, s.cambio_de_plan = pago.plan, None, None
    else:
        s.plan_proximo, s.cambio_de_plan = pago.plan, c['desde']
    s.pagado_hasta = c['hasta']


def cambiar_plan_si_toca(s, hoy):
    """El plan más barato que se pagó para después entra en vigencia cuando se terminó lo anterior."""
    if s.plan_proximo_id and s.cambio_de_plan and hoy >= s.cambio_de_plan:
        s.plan, s.plan_proximo, s.cambio_de_plan = s.plan_proximo, None, None
        return True
    return False


def avisos_del_dia(s, hoy):
    """Los avisos que tocan hoy, como claves únicas (se mandan una sola vez): 'vence-7:2026-12-01', etc."""
    hasta = cubierto_hasta(s)
    claves = []
    for antes in AVISOS_DE_VENCIMIENTO:
        if (hasta - hoy).days == antes:
            claves.append(f'vence-{antes}:{hasta}')
    e = estado(s, hoy)
    if e in (VENCIDA, SOLO_LECTURA, SUSPENDIDA, PARA_BORRAR):
        claves.append(f'{e}:{hasta}')
    for antes in AVISOS_DE_BORRADO:
        if (hasta + timedelta(days=BORRAR) - hoy).days == antes:
            claves.append(f'borrado-{antes}:{hasta}')
    return claves
