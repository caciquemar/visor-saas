"""Vistas dentro de /<taller>/. El middleware ya puso request.taller y request.membresia y filtra todo por
taller: acá no se filtra a mano. El argumento `taller` de la URL no se usa (es el mismo que request.taller)."""
from django.conf import settings
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.views.decorators.http import require_POST

from . import pin as pines
from .archivos import abrir_de_taller
from .formularios import FormDatosPin, FormMarca, FormMiembro, FormPersona, FormPin, FormRol, roles_que_puede_dar
from .mails import NO_SALIO
from .menu import secciones
from .mails import invitar as mandar_invitacion
from .mails import reenviar as mandar_de_nuevo
from .mails import link_absoluto
from .models import Invitacion, LinkDeEntrada, Membresia, Rol
from .roles import con_permiso, miembro, puede
DIAS_INVITACION_VENCIDA = 30      # en Equipo se siguen viendo (para reenviarlas) hasta 30 días después de vencer


def a_equipo(request, ver=''):
    destino = reverse('taller:equipo', kwargs={'taller': request.taller.slug})
    return redirect(destino + (f'?ver={ver}' if ver else ''))


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


SECCIONES_EQUIPO = [('personas', 'Personas', 'equipo'), ('roles', 'Roles', 'roles')]


@con_permiso('equipo', 'roles')
def equipo(request, taller, form_persona=None):
    """Equipo (ficha 23), en dos secciones: Personas (miembros e invitaciones sin usar, en una tabla, y Agregar
    persona) y Roles (los roles del taller con sus permisos)."""
    secciones = [(c, n) for c, n, permiso in SECCIONES_EQUIPO if puede(request, permiso)]
    ver = request.GET.get('ver', '')
    ver = ver if ver in dict(secciones) else secciones[0][0]
    contexto = {'ver': ver, 'secciones': secciones, 'ahora': timezone.now()}
    if ver == 'personas':
        contexto.update(
            miembros=Membresia.objects.select_related('usuario', 'rol').order_by('-activa', 'usuario__nombre'),
            invitaciones=invitaciones_sin_usar(),
            roles=roles_que_puede_dar(request.membresia),
            form_persona=form_persona or FormPersona(membresia=request.membresia))
    else:
        contexto['roles'] = Rol.objects.annotate(
            personas=Count('membresias', filter=Q(membresias__activa=True))).order_by('orden', 'pk')
    return render(request, 'talleres/equipo.html', contexto, status=400 if form_persona else 200)


@require_POST
@con_permiso('equipo')
def agregar_persona(request, taller):
    """Sin mail (rol que entra con PIN): se le arma la cuenta con usuario y PIN. Con mail: le llega la invitación."""
    form = FormPersona(request.POST, membresia=request.membresia)
    if not form.is_valid():
        return equipo(request, taller=taller, form_persona=form)
    d = form.cleaned_data
    if d['entra'] == 'pin':
        with transaction.atomic():
            usuario = get_user_model().objects.create_user(email=None, nombre=d['nombre'], usuario=d['usuario'])
            membresia = Membresia.objects.create(usuario=usuario, rol=d['rol'])
            pines.asignar_pin(membresia, d['pin'])
        messages.success(request, f'{usuario} ya puede entrar con el usuario «{usuario.usuario}» y su PIN.')
        return a_equipo(request)
    inv = mandar_invitacion(request.taller, d['email'], d['rol'], request.user)
    if inv.mail_enviado:
        messages.success(request, f'Invitación enviada a {inv.email} ({d["nombre"]}).')
    else:
        messages.error(request, NO_SALIO)
    return a_equipo(request)


def invitacion_de(request, id):
    inv = get_object_or_404(Invitacion.objects.select_related('rol'), pk=id, usada__isnull=True)
    if inv.rol.es_admin and not request.membresia.es_admin:
        raise PermissionDenied('Las invitaciones de administrador las maneja un administrador.')
    return inv


@require_POST
@con_permiso('equipo')
def reenviar_invitacion(request, taller, id):
    inv = invitacion_de(request, id)
    if mandar_de_nuevo(request.taller, inv, request.user).mail_enviado:
        messages.success(request, f'Invitación reenviada a {inv.email}.')
    else:
        messages.error(request, NO_SALIO)
    return a_equipo(request)


@require_POST
@con_permiso('equipo')
def anular_invitacion(request, taller, id):
    inv = invitacion_de(request, id)
    Invitacion.objects.filter(email=inv.email, usada__isnull=True).update(vence=timezone.now() - timedelta(
        days=DIAS_INVITACION_VENCIDA + 1))          # deja de valer y no se muestra más
    messages.success(request, f'Anulaste la invitación a {inv.email}.')
    return a_equipo(request)


def quedaria_sin_admin(membresia, rol, activa):
    if not membresia.es_admin or (rol.es_admin and activa):
        return False
    return not Membresia.objects.filter(rol__base='admin', activa=True).exclude(pk=membresia.pk).exists()


@con_permiso('equipo')
def editar_miembro(request, taller, id):
    otro = get_object_or_404(Membresia.objects.select_related('usuario', 'rol'), pk=id)
    if not request.membresia.es_admin and otro.es_admin:
        raise PermissionDenied('Solo un administrador puede cambiar a otro administrador.')
    form = FormMiembro(initial={'rol': otro.rol}, membresia=request.membresia)
    form_pin = FormPin()
    # Nombre y usuario se cambian acá solo si no tiene mail (los que tienen mail ponen su nombre al aceptar la
    # invitación, y lo cambian en Mi cuenta).
    form_datos = FormDatosPin(usuario=otro.usuario) if not otro.usuario.email else None
    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion == 'guardar':
            form = FormMiembro(request.POST, membresia=request.membresia)
            if form.is_valid():
                rol, activa = form.cleaned_data['rol'], otro.activa
                if quedaria_sin_admin(otro, rol, activa):
                    messages.error(request, 'El taller tiene que tener al menos un administrador activo.')
                elif not rol.con_pin and not otro.usuario.has_usable_password():
                    messages.error(request, f'{otro.usuario} entra con PIN y no tiene mail: dale un rol que entre '
                                            f'con usuario y PIN, o invitalo por mail con el rol {rol}.')
                else:
                    otro.rol = rol
                    otro.save(update_fields=['rol'])
                    messages.success(request, f'{otro.usuario} ahora es {rol}.')
                    return a_equipo(request)
        elif accion in ('activar', 'desactivar'):
            activa = accion == 'activar'
            if otro.pk == request.membresia.pk:
                messages.error(request, 'No te podés desactivar a vos mismo.')
            elif quedaria_sin_admin(otro, otro.rol, activa):
                messages.error(request, 'El taller tiene que tener al menos un administrador activo.')
            else:
                otro.activa = activa
                otro.save(update_fields=['activa'])
                messages.success(request, f'{otro.usuario} ya puede entrar de nuevo.' if activa else
                                 f'Desactivaste a {otro.usuario}: no puede entrar más. Su nombre queda en lo que hizo.')
                return a_equipo(request)
        elif accion == 'borrar':
            if otro.pk == request.membresia.pk:
                messages.error(request, 'No te podés borrar a vos mismo.')
            elif quedaria_sin_admin(otro, otro.rol, False):
                messages.error(request, 'El taller tiene que tener al menos un administrador activo.')
            else:
                nombre = str(otro.usuario)
                otro.delete()          # solo la membresía: la cuenta queda y su nombre sigue en lo que hizo
                messages.success(request, f'Borraste a {nombre} del taller. Su nombre queda en lo que hizo.')
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


@con_permiso('roles')
def rol(request, taller, id=None):
    """Agregar o cambiar un rol: nombre, si entra con PIN y sus permisos. Borrar: solo si nadie lo tiene."""
    r = get_object_or_404(Rol, pk=id) if id else Rol(orden=Rol.objects.count())
    personas = r.membresias.filter(activa=True).count() if r.pk else 0
    if request.method == 'POST' and request.POST.get('accion') == 'borrar' and r.pk:
        if r.es_admin:
            raise PermissionDenied('El rol Administrador no se borra.')
        if r.membresias.exists() or r.invitaciones.filter(usada__isnull=True, vence__gt=timezone.now()).exists():
            messages.error(request, f'{r} lo tienen {r.membresias.count()} persona(s) o una invitación: pasalas a '
                                    'otro rol antes de borrarlo (también a las inactivas).')
            return redirect('taller:rol', taller=request.taller.slug, id=r.pk)
        r.invitaciones.all().delete()               # vencidas o usadas: ya no sirven
        nombre = r.nombre
        r.delete()
        messages.success(request, f'Borraste el rol {nombre}.')
        return a_equipo(request, 'roles')
    form = FormRol(request.POST or None, instance=r)
    if request.method == 'POST' and form.is_valid():
        nuevo = form.save(commit=False)
        sin_mail = r.pk and not nuevo.con_pin and r.membresias.filter(usuario__email__isnull=True).exists()
        if sin_mail:
            form.add_error('con_pin', 'Hay personas con este rol que entran con PIN y no tienen mail: no podrían '
                                      'entrar más. Pasalas a otro rol primero.')
        else:
            nuevo.save()
            messages.success(request, f'Guardaste el rol {nuevo}.')
            return a_equipo(request, 'roles')
    return render(request, 'talleres/rol.html', {'rol': r, 'form': form, 'personas': personas},
                  status=400 if form.is_bound else 200)


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


@con_permiso('marca')
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
