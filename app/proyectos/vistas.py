"""Proyectos y materiales del taller: /<taller>/proyectos/... y /<taller>/materiales/. Como en talleres/vistas.py,
el middleware ya filtra todo por taller: acá no se filtra a mano. Todos los miembros ven los proyectos; subir,
cambiar de versión y la biblioteca de materiales son para el dueño y la oficina."""
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from conversor.polyboard_a_app import clave
from talleres.archivos import abrir_de_taller
from talleres.roles import Rol, con_rol, miembro

from .archivos import solo_nombre
from .formularios import FormMaterial, FormProyectoNuevo, FormSubida
from .models import Material, Original, Proyecto, Version
from .tareas import encolar

GESTION = (Rol.DUENO, Rol.OFICINA)


def a_proyecto(request, proyecto):
    return redirect('taller:proyectos:ver', taller=request.taller.slug, id=proyecto.pk)


def pantalla_de_subida(request, form, proyecto):
    return render(request, 'proyectos/subir.html', {'form': form, 'proyecto': proyecto,
                                                    'max_dxf': settings.MAX_DXF_MB},
                  status=400 if form.is_bound else 200)


def crear_version(proyecto, usuario, archivos=None, copiar_de=None):
    """Versión nueva del proyecto, en cola. Con `archivos` (dxf, [ocps]) guarda lo subido; con `copiar_de` usa
    los mismos originales de esa versión (volver a convertir), sin duplicar los archivos."""
    Proyecto.objects.select_for_update().filter(pk=proyecto.pk).first()      # numerar de a una
    numero = (proyecto.versiones.aggregate(n=Max('numero'))['n'] or 0) + 1
    version = Version.objects.create(proyecto=proyecto, numero=numero, subida_por=usuario)
    if copiar_de is not None:
        for o in copiar_de.originales.all():
            Original.objects.create(version=version, tipo=o.tipo, nombre=o.nombre, archivo=o.archivo.name,
                                    tamano=o.tamano)
    else:
        dxf, ocps = archivos
        for tipo, archivo in [(Original.Tipo.DXF, dxf)] + [(Original.Tipo.OCP, o) for o in ocps]:
            Original.objects.create(version=version, tipo=tipo, nombre=solo_nombre(archivo.name)[:255],
                                    archivo=archivo, tamano=archivo.size)
    proyecto.save(update_fields=['actualizado'])
    encolar(version)
    return version


@miembro
def lista(request, taller):
    proyectos = list(Proyecto.objects.select_related('version_actual').prefetch_related('versiones'))
    for p in proyectos:
        p.ultima = max(p.versiones.all(), key=lambda v: v.numero, default=None)
    return render(request, 'proyectos/lista.html', {'proyectos': proyectos,
                                                    'gestiona': request.membresia.rol in GESTION})


@con_rol(*GESTION)
def nuevo(request, taller):
    form = FormProyectoNuevo(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        dxf, ocps = form.cleaned_data['archivos']
        with transaction.atomic():
            proyecto = Proyecto.objects.create(nombre=form.cleaned_data['nombre'].strip()
                                               or Path(solo_nombre(dxf.name)).stem[:150],
                                               creado_por=request.user)
            crear_version(proyecto, request.user, archivos=(dxf, ocps))
        messages.success(request, f'Subiste {proyecto}. La conversión tarda unos minutos.')
        return a_proyecto(request, proyecto)
    return pantalla_de_subida(request, form, None)


@miembro
def ver(request, taller, id):
    proyecto = get_object_or_404(Proyecto.objects.select_related('version_actual'), pk=id)
    versiones = list(proyecto.versiones.select_related('subida_por').prefetch_related('originales'))
    for v in versiones:
        v.revisar_si_se_corto()
    base = proyecto.version_actual or next((v for v in versiones if v.estado == v.Estado.LISTO), None)
    texturas_nuevas, faltan = [], []
    if base and base.faltan_texturas:
        con_textura = set(Material.objects.filter(clave__in=[clave(n) for n in base.faltan_texturas])
                          .exclude(textura='').values_list('clave', flat=True))
        texturas_nuevas = [n for n in base.faltan_texturas if clave(n) in con_textura]
        faltan = [n for n in base.faltan_texturas if clave(n) not in con_textura]
    return render(request, 'proyectos/ver.html', {
        'proyecto': proyecto, 'versiones': versiones, 'base': base,
        'texturas_nuevas': texturas_nuevas, 'faltan': faltan,
        'en_proceso': any(v.en_proceso for v in versiones),
        'gestiona': request.membresia.rol in GESTION,
    })


@con_rol(*GESTION)
def nueva_version(request, taller, id):
    proyecto = get_object_or_404(Proyecto, pk=id)
    form = FormSubida(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            version = crear_version(proyecto, request.user, archivos=form.cleaned_data['archivos'])
        messages.success(request, f'Subiste la versión {version.numero}. La conversión tarda unos minutos.')
        return a_proyecto(request, proyecto)
    return pantalla_de_subida(request, form, proyecto)


@require_POST
@con_rol(*GESTION)
def usar_version(request, taller, id, numero):
    proyecto = get_object_or_404(Proyecto, pk=id)
    version = get_object_or_404(proyecto.versiones, numero=numero, estado=Version.Estado.LISTO)
    proyecto.version_actual = version
    proyecto.save(update_fields=['version_actual', 'actualizado'])
    messages.success(request, f'Ahora se usa la versión {version.numero}.')
    return a_proyecto(request, proyecto)


@require_POST
@con_rol(*GESTION)
def reconvertir(request, taller, id, numero):
    proyecto = get_object_or_404(Proyecto, pk=id)
    origen = get_object_or_404(proyecto.versiones, numero=numero)
    with transaction.atomic():
        version = crear_version(proyecto, request.user, copiar_de=origen)
    messages.success(request, f'Se está convirtiendo de nuevo como versión {version.numero}.')
    return a_proyecto(request, proyecto)


@con_rol(*GESTION)
def original(request, taller, id, numero, original_id):
    o = get_object_or_404(Original, pk=original_id, version__numero=numero, version__proyecto_id=id)
    return abrir_de_taller(request, o.archivo.name, descarga=True, nombre=o.nombre)


@con_rol(*GESTION)
def materiales(request, taller):
    lista = sorted(Material.objects.all(), key=lambda m: (bool(m.textura), m.clave))
    return render(request, 'proyectos/materiales.html', {
        'materiales': [(m, FormMaterial(instance=m, auto_id=f'm{m.pk}_%s')) for m in lista],
        'faltan': sum(1 for m in lista if not m.textura),
    })


@require_POST
@con_rol(*GESTION)
def material(request, taller, id):
    m = get_object_or_404(Material, pk=id)
    tenia_textura = bool(m.textura)
    form = FormMaterial(request.POST, request.FILES, instance=m)
    if not form.is_valid():
        messages.error(request, f'{m}: ' + ' '.join(e for errores in form.errors.values() for e in errores))
        return redirect('taller:proyectos:materiales', taller=request.taller.slug)
    form.save()
    if m.textura and not tenia_textura:
        messages.success(request, f'Se guardó la textura de {m}. En los proyectos que la usan, tocá '
                                  '"Volver a convertir" para verla.')
    else:
        messages.success(request, f'Se guardó {m}.')
    return redirect('taller:proyectos:materiales', taller=request.taller.slug)


@con_rol(*GESTION)
def imagen_material(request, taller, id):
    m = get_object_or_404(Material, pk=id)
    if not m.textura:
        return redirect('taller:proyectos:materiales', taller=request.taller.slug)
    return abrir_de_taller(request, m.textura.name)
