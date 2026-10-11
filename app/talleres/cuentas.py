"""Vistas de fuera de un taller: entrar (con mail y contraseña o con usuario y PIN), elegir taller, salir y
aceptar invitaciones. Usan `sin_filtro` porque todavía no hay taller en el contexto (archivo permitido en
separacion.py)."""
from django import forms
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView, redirect_to_login
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from usuarios.models import normalizar_usuario

from . import pin as pines
from .formularios import FormCuentaNueva
from .models import Invitacion, Membresia
from .pin import SESION_PIN
from .separacion import con_taller
from .vistas import ip_de

BACKEND = 'django.contrib.auth.backends.ModelBackend'
PIN_INCORRECTO = 'Usuario o PIN incorrectos.'


def slug_de(siguiente):
    """'/nord-good/e/X' -> 'nord-good' (el taller al que se quiere volver después de entrar), o ''."""
    from .middleware import partes_de_taller
    partes = partes_de_taller(siguiente) if (siguiente or '').startswith('/') else None
    return partes[0] if partes else ''


def membresia_por_pin(request, usuario, pin, siguiente=''):
    """La membresía con PIN de ese usuario cuyo PIN coincide (si está en varios talleres, primero el de
    `siguiente`). Lanza ValidationError con el mensaje para la pantalla. Un usuario que no existe responde igual
    que un PIN incorrecto y suma al límite por IP."""
    ip = ip_de(request)
    try:
        pines.revisar_ip(ip)
    except pines.PinBloqueado as e:
        raise forms.ValidationError(str(e))
    membresias = list(Membresia.sin_filtro.select_related('taller', 'usuario').filter(
        usuario__usuario=normalizar_usuario(usuario), usuario__is_active=True, usuario__is_staff=False,
        activa=True, taller__activo=True, rol__in=Membresia.ROLES_CON_PIN).exclude(pin='').order_by('pk'))
    preferido = slug_de(siguiente)
    membresias.sort(key=lambda m: m.taller.slug != preferido)
    bloqueo = None
    for m in membresias:
        with con_taller(m.taller):
            try:
                if pines.probar_pin(m, pin):
                    return m
            except pines.PinBloqueado as e:
                bloqueo = bloqueo or e
    pines.fallo_de_ip(ip)
    raise forms.ValidationError(str(bloqueo) if bloqueo else PIN_INCORRECTO)


class FormEntrar(AuthenticationForm):
    """Un solo formulario: con @ es mail y contraseña; sin @, usuario y PIN."""
    error_messages = {**AuthenticationForm.error_messages, 'invalid_login': 'Mail o contraseña incorrectos.'}

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        self.fields['username'].label = 'Mail o usuario'
        self.fields['password'].label = 'Contraseña o PIN'
        self.membresia_pin = None

    def clean(self):
        identificador = (self.cleaned_data.get('username') or '').strip()
        if '@' in identificador or not identificador:
            return super().clean()
        self.membresia_pin = membresia_por_pin(self.request, identificador, self.cleaned_data.get('password') or '',
                                               self.data.get('next') or self.request.GET.get('next', ''))
        self.user_cache = self.membresia_pin.usuario
        self.user_cache.backend = BACKEND
        return self.cleaned_data


class Entrar(LoginView):
    """La única pantalla para entrar: dueño y oficina con mail y contraseña; armadores e instaladores con su
    usuario y PIN. La sesión de PIN dura 12 horas y vale solo en el taller de ese PIN."""
    template_name = 'cuentas/entrar.html'
    authentication_form = FormEntrar
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        # En el celular compartido, con una sesión de PIN abierta el siguiente puede entrar sin tocar Salir.
        if request.session.get(SESION_PIN) is not None:
            self.redirect_authenticated_user = False
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        respuesta = super().form_valid(form)              # entra (y cambia la sesión)
        sesion = self.request.session
        m = form.membresia_pin
        if m is None:
            sesion.pop(SESION_PIN, None)
            sesion.set_expiry(None)
            return respuesta
        sesion[SESION_PIN] = m.taller_id
        sesion.set_expiry(pines.HORAS_SESION_PIN * 3600)
        if slug_de(self.get_redirect_url()) != m.taller.slug:
            return redirect('taller:inicio', taller=m.taller.slug)
        return respuesta


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
    logout(request)
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
