"""Vistas dentro de /<taller>/. El middleware ya puso request.taller y request.membresia y filtra todo por
taller: acá no se filtra a mano. El argumento `taller` de la URL no se usa (es el mismo que request.taller)."""
from django.conf import settings
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.views.decorators.http import require_POST

from . import pin as pines
from .archivos import abrir_de_taller
from .formularios import (FormAltaConPin, FormInvitar, FormMarca, FormMiembro, FormPin, FormDatosPin,
                          roles_que_puede_dar)
from .mails import NO_SALIO
from .menu import secciones
from .mails import invitar as mandar_invitacion
from .mails import reenviar as mandar_de_nuevo
from .mails import link_absoluto
from .models import Invitacion, LinkDeEntrada, Membresia
from .roles import Rol, con_rol, miembro

GESTION = (Rol.DUENO, Rol.OFICINA)
DIAS_INVITACION_VENCIDA = 30      # en Equipo se siguen viendo (para reenviarlas) hasta 30 días después de vencer


def a_equipo(request):
    return redirect('taller:equipo', taller=request.taller.slug)


@miembro
def inicio(request, taller):
    return render(request, 'talleres/inicio.html', {'secciones': secciones(request)})


@miembro
def seccion(request, taller, seccion):
    """La pantalla de una sección del Inicio (Armado, Producción, Configuración): sus pantallas, según el rol."""
    esta = next((s for s in secciones(request) if s['clave'] == seccion and not s['directa']), None)
    if esta is None:
        raise PermissionDenied('Tu rol no tiene acceso a esta pantalla.')
    return render(request, 'talleres/seccion.html', {'seccion': esta})


def invitaciones_sin_usar():
    """Vigentes y vencidas hace poco (para reenviarlas), la más nueva de cada mail (al reenviar, la vieja queda
    anulada y no se muestra)."""
    por_mail = {}
    for inv in Invitacion.objects.filter(usada__isnull=True, vence__gt=timezone.now() - timedelta(
            days=DIAS_INVITACION_VENCIDA)).order_by('-creada', '-pk'):
        por_mail.setdefault(inv.email, inv)
    return list(por_mail.values())


@con_rol(*GESTION)
def equipo(request, taller):
    return render(request, 'talleres/equipo.html', {
        'miembros': Membresia.objects.select_related('usuario').order_by('-activa', 'usuario__nombre'),
        'invitaciones': invitaciones_sin_usar(),
        'ahora': timezone.now(),
        'form_invitar': FormInvitar(membresia=request.membresia),
        'form_alta': FormAltaConPin(),
    })


@require_POST
@con_rol(*GESTION)
def invitar(request, taller):
    form = FormInvitar(request.POST, membresia=request.membresia)
    if form.is_valid():
        inv = mandar_invitacion(request.taller, form.cleaned_data['email'], form.cleaned_data['rol'], request.user)
        if inv.mail_enviado:
            messages.success(request, f'Invitación enviada a {inv.email}.')
        else:
            messages.error(request, NO_SALIO)
    else:
        messages.error(request, ' '.join(e for errores in form.errors.values() for e in errores))
    return a_equipo(request)


@require_POST
@con_rol(*GESTION)
def reenviar_invitacion(request, taller, id):
    inv = get_object_or_404(Invitacion, pk=id, usada__isnull=True)
    if inv.rol not in dict(roles_que_puede_dar(request.membresia)):
        raise PermissionDenied
    if mandar_de_nuevo(request.taller, inv, request.user).mail_enviado:
        messages.success(request, f'Invitación reenviada a {inv.email}.')
    else:
        messages.error(request, NO_SALIO)
    return a_equipo(request)


@require_POST
@con_rol(*GESTION)
def alta_con_pin(request, taller):
    form = FormAltaConPin(request.POST)
    if not form.is_valid():
        messages.error(request, ' '.join(e for errores in form.errors.values() for e in errores))
        return a_equipo(request)
    with transaction.atomic():
        usuario = get_user_model().objects.create_user(email=None, nombre=form.cleaned_data['nombre'],
                                                       usuario=form.cleaned_data['usuario'])
        membresia = Membresia.objects.create(usuario=usuario, rol=form.cleaned_data['rol'])
        pines.asignar_pin(membresia, form.cleaned_data['pin'])
    messages.success(request, f'{usuario} ya puede entrar con el usuario «{usuario.usuario}» y su PIN.')
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
    # Nombre y usuario se cambian acá solo si no tiene mail (los que tienen mail ponen su nombre al aceptar la
    # invitación).
    form_datos = FormDatosPin(usuario=otro.usuario) if not otro.usuario.email else None
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
        elif accion == 'datos' and form_datos is not None:
            form_datos = FormDatosPin(request.POST, usuario=otro.usuario)
            if form_datos.is_valid():
                otro.usuario.nombre = form_datos.cleaned_data['nombre']
                otro.usuario.usuario = form_datos.cleaned_data['usuario']
                otro.usuario.save(update_fields=['nombre', 'usuario'])
                messages.success(request, f'Se guardaron los datos de {otro.usuario} '
                                          f'(entra con el usuario «{otro.usuario.usuario}»).')
                return a_equipo(request)
        elif accion == 'link_entrada' and otro.usa_pin:
            # El token solo se muestra ahora: no queda guardado (en la base, su hash). Uno nuevo anula el anterior.
            _, token = LinkDeEntrada.nuevo(otro, request.user)
            link = link_absoluto(reverse('entrada', args=[token]))
            texto = (f'Hola {otro.usuario.nombre or otro.usuario}, con este link entrás a {request.taller.nombre} '
                     f'desde tu celular (vale {LinkDeEntrada.HORAS} horas, una sola vez): {link}')
            return render(request, 'talleres/miembro.html', {
                'otro': otro, 'form': form, 'form_pin': form_pin, 'form_datos': form_datos,
                'bloqueado': pines.bloqueado_del_todo(otro), 'link_entrada': link,
                'whatsapp': 'https://wa.me/?' + urlencode({'text': texto}), 'llaves': otro.usuario.llaves.all()})
        elif accion == 'quitar_llaves':
            cuantas, _ = otro.usuario.llaves.all().delete()
            messages.success(request, f'Se quitaron las huellas de {otro.usuario} ({cuantas}). Ahora entra con su '
                                      f'PIN o contraseña.')
            return a_equipo(request)
        elif accion == 'desbloquear':
            pines.desbloquear(otro)
            messages.success(request, f'PIN de {otro.usuario} desbloqueado.')
            return a_equipo(request)
    return render(request, 'talleres/miembro.html', {'otro': otro, 'form': form, 'form_pin': form_pin,
                                                     'form_datos': form_datos, 'llaves': otro.usuario.llaves.all(),
                                                     'bloqueado': pines.bloqueado_del_todo(otro)})


def ip_de(request):
    """IP de quien entra. Detrás del túnel de Cloudflare todo llega desde cloudflared: la de verdad viene en
    CF-Connecting-IP (solo se le cree con DETRAS_DE_CLOUDFLARE=1)."""
    if settings.DETRAS_DE_CLOUDFLARE and request.META.get('HTTP_CF_CONNECTING_IP'):
        return request.META['HTTP_CF_CONNECTING_IP']
    return request.META.get('REMOTE_ADDR', '')


def siguiente_del_taller(request):
    """Adónde volver después de entrar con PIN (`next`): solo una dirección de este mismo taller; si no, ''."""
    siguiente = request.POST.get('next') or request.GET.get('next') or ''
    if not url_has_allowed_host_and_scheme(siguiente, allowed_hosts={request.get_host()}):
        return ''
    if not siguiente.startswith(f'/{request.taller.slug}/') or siguiente.startswith(f'/{request.taller.slug}/pin/'):
        return ''
    return siguiente


def entrar_con_pin(request, taller):
    """Dirección vieja de la pantalla de PIN: ahora todos entran en /entrar/ (con usuario y PIN)."""
    siguiente = siguiente_del_taller(request) or reverse('taller:inicio', kwargs={'taller': request.taller.slug})
    return redirect(f"{reverse('entrar')}?{urlencode({'next': siguiente})}")


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
