"""Proyectos y materiales del taller: /<taller>/proyectos/... y /<taller>/materiales/. Como en talleres/vistas.py,
el middleware ya filtra todo por taller: acá no se filtra a mano. Todos los miembros ven los proyectos; subir,
cambiar de versión y la biblioteca de materiales son para el dueño y la oficina."""
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Max
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from conversor.polyboard_a_app import clave
from modulos import registro
from talleres.archivos import abrir_de_taller
from talleres.roles import Rol, con_rol, miembro

from .archivos import solo_nombre
from .formularios import FormMaterial, FormProyectoNuevo, FormSinCanto, FormSubida
from .models import LinkCliente, Material, Original, Proyecto, Version
from .tareas import encolar
from .visor import url_de_link

GESTION = (Rol.DUENO, Rol.OFICINA)


def a_proyecto(request, proyecto):
    return redirect('taller:proyectos:ver', taller=request.taller.slug, id=proyecto.pk)


def formulario(clase, request):
    """Formulario de subida con los campos que suman los módulos prendidos del taller."""
    form = clase(request.POST or None, request.FILES or None)
    for modulo in registro.activos():
        modulo.campos_de_subida(form)
    return form


def pantalla_de_subida(request, form, proyecto):
    extras = [modulo.html_de_subida(form) for modulo in registro.activos()]
    return render(request, 'proyectos/subir.html', {'form': form, 'proyecto': proyecto,
                                                    'max_dxf': settings.MAX_DXF_MB, 'extras': extras},
                  status=400 if form.is_bound else 200)


def crear_version(proyecto, usuario, archivos=None, copiar_de=None, datos=None):
    """Versión nueva del proyecto, en cola. Con `archivos` (dxf, [ocps]) guarda lo subido (y `datos`, lo que el
    formulario trae para los módulos); con `copiar_de` usa los mismos originales de esa versión (volver a
    convertir), sin duplicar los archivos."""
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
        for modulo in registro.activos():
            modulo.al_guardar_version(version, datos or {})
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
    form = formulario(FormProyectoNuevo, request)
    if request.method == 'POST' and form.is_valid():
        dxf, ocps = form.cleaned_data['archivos']
        with transaction.atomic():
            proyecto = Proyecto.objects.create(nombre=form.cleaned_data['nombre'].strip()
                                               or Path(solo_nombre(dxf.name)).stem[:150],
                                               creado_por=request.user)
            crear_version(proyecto, request.user, archivos=(dxf, ocps), datos=form.cleaned_data)
        messages.success(request, f'Subiste {proyecto}. La conversión tarda unos minutos.')
        return a_proyecto(request, proyecto)
    return pantalla_de_subida(request, form, None)


@miembro
def ver(request, taller, id):
    proyecto = get_object_or_404(Proyecto.objects.select_related('version_actual'), pk=id)
    versiones = list(proyecto.versiones.select_related('subida_por').prefetch_related('originales'))
    modulos = registro.activos()
    for v in versiones:
        v.revisar_si_se_corto()
        v.extras = [m.html_de_version(request, proyecto, v) for m in modulos]
        v.subidos = [o for o in v.originales.all() if not registro.oculto(o, modulos)]
    base = proyecto.version_actual or next((v for v in versiones if v.estado == v.Estado.LISTO), None)
    texturas_nuevas, faltan = [], []
    if base and base.faltan_texturas:
        con_textura = set(Material.objects.filter(clave__in=[clave(f['nombre']) for f in base.faltan_texturas])
                          .exclude(textura='').values_list('tipo', 'clave'))
        for f in base.faltan_texturas:
            texto = f"{f['tipo']} {f['nombre']}"
            (texturas_nuevas if (f['tipo'], clave(f['nombre'])) in con_textura else faltan).append(texto)
    gestiona = request.membresia.rol in GESTION
    links = list(proyecto.links.filter(anulado__isnull=True)) if gestiona else []
    for link in links:
        link.direccion = url_de_link(request, link)
    return render(request, 'proyectos/ver.html', {
        'proyecto': proyecto, 'versiones': versiones, 'base': base,
        'listo': bool(proyecto.version_actual and proyecto.version_actual.estado == Version.Estado.LISTO),
        'links': links, 'dias_link': VENCIMIENTOS, 'dias_por_defecto': LinkCliente.DIAS,
        'texturas_nuevas': texturas_nuevas, 'faltan': faltan,
        'en_proceso': any(v.en_proceso or any(m.en_proceso(v) for m in modulos) for v in versiones),
        'gestiona': gestiona,
    })


@con_rol(*GESTION)
def nueva_version(request, taller, id):
    proyecto = get_object_or_404(Proyecto, pk=id)
    form = formulario(FormSubida, request)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            version = crear_version(proyecto, request.user, archivos=form.cleaned_data['archivos'],
                                    datos=form.cleaned_data)
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
    if registro.oculto(o):          # la carpeta del postprocesador, con el módulo Zicar apagado
        raise Http404()
    return abrir_de_taller(request, o.archivo.name, descarga=True, nombre=o.nombre)


@con_rol(*GESTION)
def materiales(request, taller):
    lista = sorted(Material.objects.all(), key=lambda m: (bool(m.textura), m.clave))
    grupos = [(etiqueta, [(m, FormMaterial(instance=m, auto_id=f'm{m.pk}_%s')) for m in lista if m.tipo == tipo])
              for tipo, etiqueta in (('tablero', 'Tableros'), ('canto', 'Cantos'))]
    return render(request, 'proyectos/materiales.html', {
        'grupos': [(etiqueta, mats) for etiqueta, mats in grupos if mats],
        'faltan': sum(1 for m in lista if not m.textura),
        'form_sin_canto': FormSinCanto(instance=request.taller),
    })


@require_POST
@con_rol(*GESTION)
def sin_canto(request, taller):
    form = FormSinCanto(request.POST, instance=request.taller)
    if form.is_valid():
        form.save()
        messages.success(request, 'Guardaste el color de los lados sin canto. En el visor ya se ve; para la realidad '
                                  'aumentada del link del cliente, tocá "Volver a convertir" en cada proyecto.')
    else:
        messages.error(request, ' '.join(e for errores in form.errors.values() for e in errores))
    return redirect('taller:proyectos:materiales', taller=request.taller.slug)


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


VENCIMIENTOS = [(30, '30 días'), (90, '90 días'), (365, 'un año'), (0, 'no vence')]


@require_POST
@con_rol(*GESTION)
def nuevo_link(request, taller, id):
    proyecto = get_object_or_404(Proyecto, pk=id)
    try:
        dias = int(request.POST.get('dias', LinkCliente.DIAS))
    except ValueError:
        dias = -1
    if dias not in dict(VENCIMIENTOS):
        messages.error(request, 'Elegí cuándo vence el link.')
        return a_proyecto(request, proyecto)
    LinkCliente.objects.create(proyecto=proyecto, creado_por=request.user,
                               vence=timezone.now() + timedelta(days=dias) if dias else None)
    messages.success(request, 'Listo el link para el cliente. Copialo y mandáselo.')
    return a_proyecto(request, proyecto)


@require_POST
@con_rol(*GESTION)
def anular_link(request, taller, id, link_id):
    link = get_object_or_404(LinkCliente, pk=link_id, proyecto_id=id, anulado__isnull=True)
    link.anulado = timezone.now()
    link.save(update_fields=['anulado'])
    messages.success(request, 'Anulaste el link: quien lo tenga ya no puede ver el proyecto.')
    return redirect('taller:proyectos:ver', taller=request.taller.slug, id=id)
