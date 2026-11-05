"""Mi suscripción (dentro del taller), la vuelta desde la pasarela, el aviso de la pasarela y la página de pago
simulada (solo con PASARELA=simulada)."""
import json
import logging

from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from talleres.limites import NOMBRES, tope
from talleres.mails import link_absoluto
from talleres.models import Taller
from talleres.roles import con_permiso
from talleres.separacion import con_taller

from . import estados
from .models import Pago, Plan
from .pasarelas import ErrorPayway
from .servicio import (confirmar, cotizacion_vigente, estado_de, hoy, nuevo_pago, opciones, plan_vigente,
                       suscripcion_de)

log = logging.getLogger('visor.suscripciones')


def urls_de(pago):
    slug = pago.taller.slug
    return {'volver': link_absoluto(reverse('taller:suscripcion:volver', kwargs={'taller': slug, 'codigo': pago.codigo})),
            'aviso': link_absoluto(reverse('pagos:aviso', args=[slug, pago.codigo]))}


@con_permiso('suscripcion')
def pantalla(request, taller):
    s = suscripcion_de(request.taller)
    dia = hoy()
    e = estado_de(s, dia)
    planes = opciones(s, dia)
    for o in planes:
        o['funciones'] = [NOMBRES[f] for f in o['plan'].funciones or []]
    return render(request, 'suscripciones/pantalla.html', {
        's': s, 'estado': e, 'nombre_estado': estados.NOMBRES[e], 'plan': plan_vigente(s, dia),
        'hasta': estados.cubierto_hasta(s), 'en_prueba': e == estados.PRUEBA,
        'sin_cobro': s.sin_cobro_hasta and s.sin_cobro_hasta >= dia,
        'opciones': planes, 'cotizacion': cotizacion_vigente(),
        'proyectos': tope(request.taller, 'proyectos'), 'usuarios': tope(request.taller, 'usuarios'),
        'pagos': s.pagos.select_related('plan')[:24], 'activas': settings.SUSCRIPCIONES_ACTIVAS,
        'gracia': estados.GRACIA,
    })


@require_POST
@con_permiso('suscripcion')
def pagar(request, taller):
    s = suscripcion_de(request.taller)
    plan = get_object_or_404(Plan, pk=request.POST.get('plan'), a_la_venta=True)
    periodo = request.POST.get('periodo')
    if periodo not in estados.PERIODOS:
        raise Http404('Período desconocido')
    try:
        pago = nuevo_pago(s, plan, periodo, request.user, urls_de)
    except (ValueError, ErrorPayway) as e:
        messages.error(request, str(e))
        return redirect('taller:suscripcion:pantalla', taller=taller)
    return redirect(pago.link)


@con_permiso('suscripcion')
def volver(request, taller, codigo):
    """La pasarela vuelve acá después de pagar (o de cancelar): se consulta el pago en ese momento."""
    pago = get_object_or_404(Pago, codigo=codigo)
    try:
        estado = confirmar(pago, aviso=request.GET.dict())
    except Exception:
        log.exception('No se pudo consultar el pago %s al volver', pago.codigo)
        estado = pago.estado
    pago = Pago.objects.select_related('suscripcion', 'plan').get(pk=pago.pk)
    if estado == Pago.Estado.APROBADO:
        messages.success(request, f'¡Listo! Pago aprobado. Tu plan {pago.plan} quedó pago hasta el '
                                  f'{pago.suscripcion.pagado_hasta:%d/%m/%Y}.')
    elif estado == Pago.Estado.RECHAZADO:
        messages.error(request, 'El pago fue rechazado. Probá con otra tarjeta o de nuevo en un rato.')
    else:
        messages.info(request, 'Todavía no tenemos la confirmación del pago. En cuanto llegue, se actualiza solo.')
    return redirect('taller:suscripcion:pantalla', taller=taller)


@csrf_exempt
def aviso(request, slug, codigo):
    """La pasarela avisa que un pago cambió. No se le cree: se consulta. Siempre responde 200 (si no, reintenta)."""
    taller = Taller.objects.filter(slug=slug).first()
    if taller is None:
        return HttpResponse('ok')
    with con_taller(taller):
        pago = Pago.objects.filter(codigo=codigo).first()
        if pago is None:
            return HttpResponse('ok')
        try:
            datos = json.loads(request.body or b'{}') if request.body else {}
        except ValueError:
            datos = {}
        if not isinstance(datos, dict):
            datos = {}
        datos = {**request.GET.dict(), **request.POST.dict(), **datos}
        try:
            confirmar(pago, aviso=datos)
        except Exception:
            log.exception('No se pudo consultar el pago %s después del aviso', pago.codigo)
    return HttpResponse('ok')


def simulada(request, slug, codigo):
    """La "página de la pasarela" en la PC y en las pruebas: Aprobar o Rechazar y vuelve como lo haría Payway."""
    if settings.PASARELA != 'simulada':
        raise Http404()
    taller = get_object_or_404(Taller, slug=slug)
    with con_taller(taller):
        pago = get_object_or_404(Pago, codigo=codigo, pasarela='simulada')
        if request.method == 'POST':
            elegido = request.POST.get('resultado')
            if elegido in (Pago.Estado.APROBADO, Pago.Estado.RECHAZADO) and pago.estado == Pago.Estado.PENDIENTE:
                pago.datos = {**(pago.datos or {}), 'simulada': elegido}
                pago.save(update_fields=['datos'])
            return redirect(urls_de(pago)['volver'])
        return render(request, 'suscripciones/simulada.html', {'pago': pago, 'taller': taller})
