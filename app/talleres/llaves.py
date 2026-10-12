"""Entrar con la huella, el patrón o el PIN de pantalla del celular: llaves de acceso (passkeys, WebAuthn), con
py_webauthn. Solo en celulares propios (talleres/equipo_celular.py): en uno compartido, cualquiera que sepa
desbloquearlo entraría como cualquiera.

- Registrar (con sesión): /cuenta/llave/nueva/ ofrece "Usar la huella"; el celular crea la llave y la app guarda
  solo la clave pública (usuarios.LlaveDeAcceso).
- Entrar (sin sesión): llave descubrible, no hace falta escribir el usuario. La sesión que da es completa (como la
  de mail, no atada a un taller): la huella es más segura que el PIN. El middleware sigue pidiendo una membresía
  activa en cada taller.
- Los desafíos van en la sesión y vencen a los 5 minutos. Necesita HTTPS (o http://localhost en la PC: con
  127.0.0.1 el navegador no deja, porque una IP no sirve como RP ID; usar DOMINIO_APP=localhost:8000).
"""
import json
import time

from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from webauthn import (generate_authentication_options, generate_registration_options, options_to_json,
                      verify_authentication_response, verify_registration_response)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (AuthenticatorSelectionCriteria, PublicKeyCredentialDescriptor,
                                      ResidentKeyRequirement, UserVerificationRequirement)

from usuarios.models import LlaveDeAcceso

from . import equipo_celular
from .pin import SESION_PIN

BACKEND = 'django.contrib.auth.backends.ModelBackend'
SESION_DESAFIO = 'llave_desafio'
VENCE_SEGUNDOS = 300


def rp_id():
    return settings.DOMINIO_APP.split(':')[0]


def siguiente(request, por_defecto='/'):
    destino = request.POST.get('next') or request.GET.get('next') or ''
    if url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}) and destino.startswith('/'):
        return destino
    return por_defecto


def _guardar_desafio(request, tipo, opciones):
    request.session[SESION_DESAFIO] = {'tipo': tipo, 'valor': bytes_to_base64url(opciones.challenge),
                                       'hora': time.time()}


def _tomar_desafio(request, tipo):
    """El desafío pendiente de ese tipo (y lo borra: sirve una vez). None si no hay o venció."""
    d = request.session.pop(SESION_DESAFIO, None)
    if not d or d.get('tipo') != tipo or time.time() - d.get('hora', 0) > VENCE_SEGUNDOS:
        return None
    return base64url_to_bytes(d['valor'])


def _cuerpo(request):
    try:
        return json.loads(request.body or b'{}')
    except ValueError:
        return {}


def equipo_de(request):
    agente = request.META.get('HTTP_USER_AGENT', '')
    for nombre in ('iPhone', 'iPad', 'Android', 'Windows', 'Mac'):
        if nombre in agente:
            return nombre
    return 'Otro equipo'


def _no(mensaje, estado=400):
    return JsonResponse({'error': mensaje}, status=estado)


# ---------------------------------------------------------------- registrar

@login_required
def nueva(request):
    """Ofrece usar la huella en este celular. Solo en un celular propio; si no, sigue de largo."""
    if equipo_celular.leer(request)['tipo'] != equipo_celular.PROPIO:
        return redirect(siguiente(request))
    return render(request, 'cuentas/llave_nueva.html', {'siguiente': siguiente(request),
                                                       'ya_tiene': request.user.llaves.exists()})


@require_POST
@login_required
def nueva_opciones(request):
    if equipo_celular.leer(request)['tipo'] != equipo_celular.PROPIO:
        return _no('La huella se usa solo en un celular propio.', 403)
    u = request.user
    opciones = generate_registration_options(
        rp_id=rp_id(), rp_name=settings.MARCA_SERVICIO, user_id=f'visor-{u.pk}'.encode(),
        user_name=u.email or u.usuario or f'usuario-{u.pk}', user_display_name=str(u),
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED, user_verification=UserVerificationRequirement.REQUIRED),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(ll.credencial))
                             for ll in u.llaves.all()])
    _guardar_desafio(request, 'nueva', opciones)
    return JsonResponse(json.loads(options_to_json(opciones)))


@require_POST
@login_required
def nueva_guardar(request):
    desafio = _tomar_desafio(request, 'nueva')
    if desafio is None:
        return _no('Pasó mucho tiempo. Probá de nuevo.')
    try:
        v = verify_registration_response(credential=_cuerpo(request), expected_challenge=desafio,
                                         expected_rp_id=rp_id(), expected_origin=settings.URL_APP,
                                         require_user_verification=True)
    except (WebAuthnException, ValueError, KeyError, TypeError):
        return _no('El celular no pudo crear la llave. Probá de nuevo.')
    LlaveDeAcceso.objects.update_or_create(
        credencial=bytes_to_base64url(v.credential_id),
        defaults={'usuario': request.user, 'clave_publica': v.credential_public_key, 'contador': v.sign_count,
                  'equipo': equipo_de(request)})
    return JsonResponse({'ir': siguiente(request)})


# ---------------------------------------------------------------- entrar

@require_POST
def entrar_opciones(request):
    """Desafío para entrar. Con `usuario` (un nombre tocado en la lista del celular) solo valen sus llaves."""
    permitidas = None
    usuario_id = str(_cuerpo(request).get('usuario', ''))
    if usuario_id.isdigit():
        permitidas = [PublicKeyCredentialDescriptor(id=base64url_to_bytes(c)) for c in
                      LlaveDeAcceso.objects.filter(usuario_id=int(usuario_id)).values_list('credencial', flat=True)]
    opciones = generate_authentication_options(rp_id=rp_id(), allow_credentials=permitidas or None,
                                               user_verification=UserVerificationRequirement.REQUIRED)
    _guardar_desafio(request, 'entrar', opciones)
    return JsonResponse(json.loads(options_to_json(opciones)))


@require_POST
def entrar(request):
    desafio = _tomar_desafio(request, 'entrar')
    if desafio is None:
        return _no('Pasó mucho tiempo. Probá de nuevo.')
    credencial = _cuerpo(request)
    llave = (LlaveDeAcceso.objects.select_related('usuario')
             .filter(credencial=str(credencial.get('id', '')), usuario__is_active=True).first())
    if llave is None:
        return _no('Esta llave no está registrada. Entrá con tu PIN o tu contraseña.', 403)
    try:
        v = verify_authentication_response(
            credential=credencial, expected_challenge=desafio, expected_rp_id=rp_id(),
            expected_origin=settings.URL_APP, credential_public_key=bytes(llave.clave_publica),
            credential_current_sign_count=llave.contador, require_user_verification=True)
    except (WebAuthnException, ValueError, KeyError, TypeError):
        return _no('No se pudo comprobar la huella. Probá de nuevo.', 403)
    llave.contador, llave.usada = v.new_sign_count, timezone.now()
    llave.save(update_fields=['contador', 'usada'])

    login(request, llave.usuario, backend=BACKEND)
    request.session.pop(SESION_PIN, None)
    request.session.set_expiry(None)
    respuesta = JsonResponse({'ir': siguiente(request)})
    return equipo_celular.recordar(request, respuesta, llave.usuario)
