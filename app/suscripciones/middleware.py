"""Lo que la suscripción frena, en un solo lugar (va después de TallerMiddleware, dentro del taller del pedido):

- solo lectura: se ve todo, pero ningún cambio (POST, PUT, PATCH, DELETE) salvo pagar y Mi cuenta.
- suspendida o para borrar: solo "Mi suscripción" para quien la maneja; el link del cliente no anda.
- funciones del plan por sección: Producción (`avance`) necesita la función 'avance'.

Con SUSCRIPCIONES_ACTIVAS=0 no hace nada."""
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect, render

from talleres.limites import MENSAJES, permite

from . import estados
from .servicio import estado_de, suscripcion_de

SEGUROS = ('GET', 'HEAD', 'OPTIONS')
SIEMPRE = ('suscripcion/', 'cuenta/')                # dentro de /<taller>/: pagar y Mi cuenta andan siempre
FUNCION_DE_SECCION = {'avance': 'avance'}           # namespace de la dirección -> función del plan


def quiere_json(request):
    return '/api/' in request.path or 'application/json' in request.headers.get('Accept', '')


def frenar(request, mensaje, plantilla, status=403):
    if quiere_json(request):
        return JsonResponse({'error': mensaje}, status=status)
    membresia = getattr(request, 'membresia', None)
    return render(request, plantilla, {'mensaje': mensaje,
                                       'puede_pagar': membresia is not None and membresia.puede('suscripcion')},
                  status=status)


class SuscripcionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.suscripcion = request.estado_suscripcion = None
        taller = getattr(request, 'taller', None)
        if not settings.SUSCRIPCIONES_ACTIVAS or taller is None:
            return self.get_response(request)
        s = suscripcion_de(taller)
        e = estado_de(s)
        request.suscripcion, request.estado_suscripcion = s, e
        if getattr(request, 'link_cliente', None) is not None:
            if e in (estados.SUSPENDIDA, estados.PARA_BORRAR):
                return render(request, 'proyectos/link_no_disponible.html', status=404)
            return self.get_response(request)
        if getattr(request, 'membresia', None) is None:
            return self.get_response(request)
        resto = request.path_info.lstrip('/').partition('/')[2]
        if resto.startswith(SIEMPRE):
            return self.get_response(request)
        if e in (estados.SUSPENDIDA, estados.PARA_BORRAR):
            if request.membresia.puede('suscripcion') and not quiere_json(request):
                return redirect('taller:suscripcion:pantalla', taller=taller.slug)
            return frenar(request, 'La cuenta del taller está suspendida. Hablá con el administrador del taller.',
                          'suscripciones/frenado.html')
        if e == estados.SOLO_LECTURA and request.method not in SEGUROS:
            return frenar(request, 'La cuenta está en solo lectura: se ve todo, pero no se puede cambiar nada hasta '
                                   'pagar el plan.', 'suscripciones/frenado.html')
        return self.get_response(request)

    def process_view(self, request, vista, args, kwargs):
        taller = getattr(request, 'taller', None)
        if not settings.SUSCRIPCIONES_ACTIVAS or taller is None or request.resolver_match is None:
            return None
        for seccion, funcion in FUNCION_DE_SECCION.items():
            if seccion in request.resolver_match.namespaces and not permite(taller, funcion):
                return frenar(request, MENSAJES[funcion], 'suscripciones/frenado.html')
        return None
