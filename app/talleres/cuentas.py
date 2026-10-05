"""Vistas de fuera de un taller: elegir taller después de entrar, salir y aceptar invitaciones.
Usan `sin_filtro` porque todavía no hay taller en el contexto (archivo permitido en separacion.py)."""
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .formularios import FormCuentaNueva
from .models import Invitacion, Membresia, Taller
from .pin import SESION_PIN
from .separacion import con_taller

BACKEND = 'django.contrib.auth.backends.ModelBackend'


@login_required
def inicio(request):
    membresias = (Membresia.sin_filtro.select_related('taller')
                  .filter(usuario=request.user, activa=True, taller__activo=True).order_by('taller__nombre'))
    pin_taller = request.session.get(SESION_PIN)
    if pin_taller is not None:
        membresias = membresias.filter(taller_id=pin_taller)
    membresias = list(membresias)
    if len(membresias) == 1:
        return redirect('taller:inicio', taller=membresias[0].taller.slug)
    return render(request, 'cuentas/elegir_taller.html', {'membresias': membresias})


@require_POST
def salir(request):
    pin_taller = request.session.get(SESION_PIN)
    slug = Taller.objects.filter(pk=pin_taller).values_list('slug', flat=True).first() if pin_taller else None
    logout(request)
    if slug:
        return redirect('taller:pin', taller=slug)
    return redirect('entrar')


def invitacion(request, token):
    inv = (Invitacion.sin_filtro.select_related('taller')
           .filter(token_hash=Invitacion.cifrar(token)).first())
    if inv is None or not inv.vigente or not inv.taller.activo:
        return render(request, 'cuentas/invitacion_invalida.html', status=404)

    usuario = request.user if request.user.is_authenticated else None
    if usuario is not None and usuario.email != inv.email:
        return render(request, 'cuentas/invitacion_otra_cuenta.html', {'inv': inv}, status=403)

    if usuario is None:
        Usuario = get_user_model()
        existente = Usuario.objects.filter(email=inv.email).first()
        if existente is not None and existente.has_usable_password():
            return redirect_to_login(request.get_full_path())
        form = FormCuentaNueva(request.POST or None, usuario=existente or Usuario(email=inv.email))
        if request.method != 'POST' or not form.is_valid():
            return render(request, 'cuentas/invitacion.html', {'inv': inv, 'form': form})
        usuario = form.save()
        login(request, usuario, backend=BACKEND)

    with transaction.atomic(), con_taller(inv.taller):
        # Marcar usada antes de dar acceso: si se abre dos veces a la vez, solo una gana.
        if not Invitacion.objects.filter(pk=inv.pk, usada__isnull=True).update(usada=timezone.now(),
                                                                               usada_por=usuario):
            return render(request, 'cuentas/invitacion_invalida.html', status=404)
        membresia = Membresia.objects.filter(usuario=usuario).first() or Membresia(usuario=usuario)
        membresia.rol = inv.rol
        membresia.activa = True
        membresia.save()
    return redirect('taller:inicio', taller=inv.taller.slug)
