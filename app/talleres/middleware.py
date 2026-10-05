"""Pone el taller del pedido en el contexto. Es la única puerta a /<taller>/...

- Sin sesión: va a entrar (sin decir si el taller existe), salvo la pantalla de PIN.
- Taller inexistente, inactivo o del que el usuario no es miembro activo: 404, sin diferencia entre los casos.
- Sesión de PIN: solo vale en el taller donde se entró y para armadores e instaladores.
"""
from django.contrib.auth.views import redirect_to_login
from django.http import Http404

from .models import RESERVADOS, Membresia, Taller
from .pin import SESION_PIN
from .separacion import taller_actual


def partes_de_taller(ruta):
    """'/nord-good/equipo/' -> ('nord-good', 'equipo/'); None si la dirección no es de un taller."""
    slug, _, resto = ruta.lstrip('/').partition('/')
    if not slug or slug in RESERVADOS:
        return None
    return slug, resto


class TallerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.taller = request.membresia = None
        partes = partes_de_taller(request.path_info)
        if partes is None:
            return self.get_response(request)
        slug, resto = partes
        es_pin = resto == 'pin/'

        if not es_pin and not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        taller = Taller.objects.filter(slug=slug, activo=True).first()
        if taller is None:
            raise Http404('No existe el taller')

        if not es_pin:
            membresia = (Membresia.sin_filtro.select_related('usuario')
                         .filter(taller=taller, usuario=request.user, activa=True).first())
            if membresia is None:
                raise Http404('No existe el taller')
            pin_taller = request.session.get(SESION_PIN)
            if pin_taller is not None and (pin_taller != taller.pk or not membresia.usa_pin):
                raise Http404('No existe el taller')
            request.membresia = membresia

        request.taller = taller
        marca = taller_actual.set(taller)
        try:
            return self.get_response(request)
        finally:
            taller_actual.reset(marca)
