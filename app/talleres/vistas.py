"""Vistas dentro de /<taller>/. El middleware ya puso request.taller y request.membresia y filtra todo por
taller: acá no se filtra a mano. El argumento `taller` de la URL no se usa (es el mismo que request.taller)."""
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import pin as pines
from .archivos import abrir_de_taller
from .formularios import FormAltaConPin, FormInvitar, FormMarca, FormMiembro, FormPin
from .mails import invitar as mandar_invitacion
from .models import Invitacion, Membresia
from .roles import Rol, con_rol, miembro

GESTION = (Rol.DUENO, Rol.OFICINA)


def a_equipo(request):
    return redirect('taller:equipo', taller=request.taller.slug)


@miembro
def inicio(request, taller):
    return render(request, 'talleres/inicio.html')


@con_rol(*GESTION)
def equipo(request, taller):
    return render(request, 'talleres/equipo.html', {
        'miembros': Membresia.objects.select_related('usuario').order_by('-activa', 'usuario__nombre'),
        'invitaciones': Invitacion.objects.filter(usada__isnull=True, vence__gt=timezone.now()),
        'form_invitar': FormInvitar(membresia=request.membresia),
        'form_alta': FormAltaConPin(),
    })


@require_POST
@con_rol(*GESTION)
def invitar(request, taller):
    form = FormInvitar(request.POST, membresia=request.membresia)
    if form.is_valid():
        mandar_invitacion(request.taller, form.cleaned_data['email'], form.cleaned_data['rol'], request.user)
        messages.success(request, f'Invitación enviada a {form.cleaned_data["email"]}.')
    else:
        messages.error(request, ' '.join(e for errores in form.errors.values() for e in errores))
    return a_equipo(request)


@require_POST
@con_rol(*GESTION)
def alta_con_pin(request, taller):
    form = FormAltaConPin(request.POST)
    if not form.is_valid():
        messages.error(request, ' '.join(e for errores in form.errors.values() for e in errores))
        return a_equipo(request)
    with transaction.atomic():
        usuario = get_user_model().objects.create_user(email=None, nombre=form.cleaned_data['nombre'])
        membresia = Membresia.objects.create(usuario=usuario, rol=form.cleaned_data['rol'])
        pines.asignar_pin(membresia, form.cleaned_data['pin'])
    messages.success(request, f'{usuario} ya puede entrar con su PIN.')
    return a_equipo(request)


def quedaria_sin_dueno(membresia, rol, activa):
    if membresia.rol != Rol.DUENO or (rol == Rol.DUENO and activa):
        return False
    return not Membresia.objects.filter(rol=Rol.DUENO, activa=True).exclude(pk=membresia.pk).exists()


@con_rol(*GESTION)
def editar_miembro(request, taller, id):
    otro = get_object_or_404(Membresia.objects.select_related('usuario'), pk=id)
    if request.membresia.rol != Rol.DUENO and otro.rol == Rol.DUENO:
        raise PermissionDenied('Solo un dueño puede cambiar a otro dueño.')
    form = FormMiembro(initial={'rol': otro.rol, 'activa': otro.activa}, membresia=request.membresia)
    form_pin = FormPin()
    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion == 'guardar':
            form = FormMiembro(request.POST, membresia=request.membresia)
            if form.is_valid():
                rol, activa = form.cleaned_data['rol'], form.cleaned_data['activa']
                if quedaria_sin_dueno(otro, rol, activa):
                    messages.error(request, 'El taller tiene que tener al menos un dueño activo.')
                else:
                    otro.rol, otro.activa = rol, activa
                    otro.save(update_fields=['rol', 'activa'])
                    messages.success(request, f'Se guardaron los cambios de {otro.usuario}.')
                    return a_equipo(request)
        elif accion == 'pin' and otro.usa_pin:
            form_pin = FormPin(request.POST)
            if form_pin.is_valid():
                pines.asignar_pin(otro, form_pin.cleaned_data['pin'])
                messages.success(request, f'PIN de {otro.usuario} cambiado.')
                return a_equipo(request)
        elif accion == 'desbloquear':
            pines.desbloquear(otro)
            messages.success(request, f'PIN de {otro.usuario} desbloqueado.')
            return a_equipo(request)
    return render(request, 'talleres/miembro.html', {'otro': otro, 'form': form, 'form_pin': form_pin,
                                                     'bloqueado': pines.bloqueado_del_todo(otro)})


def ip_de(request):
    # En la ficha 07 (detrás de Cloudflare) cambiar por CF-Connecting-IP.
    return request.META.get('REMOTE_ADDR', '')


def entrar_con_pin(request, taller):
    """Pública (sin sesión): cualquiera con la dirección del taller la ve. Ver talleres/pin.py."""
    candidatos = (Membresia.objects.select_related('usuario')
                  .filter(rol__in=Membresia.ROLES_CON_PIN, activa=True, usuario__is_active=True,
                          usuario__is_staff=False)
                  .exclude(pin='').order_by('usuario__nombre'))
    error, elegido = None, request.POST.get('miembro', '')
    if request.method == 'POST':
        m = candidatos.filter(pk=int(elegido)).first() if elegido.isdigit() else None
        if m is None:
            error = 'Tocá tu nombre.'
        else:
            try:
                correcto = pines.probar_pin(m, request.POST.get('pin', ''), ip_de(request))
            except pines.PinBloqueado as e:
                error = str(e)
            else:
                if correcto:
                    login(request, m.usuario, backend='django.contrib.auth.backends.ModelBackend')
                    request.session[pines.SESION_PIN] = request.taller.pk
                    request.session.set_expiry(pines.HORAS_SESION_PIN * 3600)
                    return redirect('taller:inicio', taller=request.taller.slug)
                error = 'PIN incorrecto.'
    return render(request, 'talleres/pin.html', {'candidatos': candidatos, 'error': error, 'elegido': elegido},
                  status=200 if error is None else 400)


@con_rol(Rol.DUENO)
def marca(request, taller):
    t = request.taller
    anterior = t.logo.name if t.logo else ''
    form = FormMarca(request.POST or None, request.FILES or None, instance=t)
    if request.method == 'POST' and form.is_valid():
        t = form.save(commit=False)
        if request.POST.get('quitar_logo') and not request.FILES.get('logo'):
            t.logo = ''
        t.save(update_fields=['logo', 'color'])
        if anterior and anterior != (t.logo.name if t.logo else ''):
            t.logo.storage.delete(anterior)
        messages.success(request, 'Guardaste la marca del taller.')
        return redirect('taller:marca', taller=t.slug)
    return render(request, 'talleres/marca.html', {'form': form}, status=400 if form.is_bound else 200)


@miembro
def logo(request, taller):
    if not request.taller.logo:
        raise Http404()
    return abrir_de_taller(request, request.taller.logo.name)
