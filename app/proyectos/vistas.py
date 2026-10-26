"""Proyectos y materiales del taller: /<taller>/proyectos/... y /<taller>/materiales/. Como en talleres/vistas.py,
el middleware ya filtra todo por taller: acá no se filtra a mano. Todos los miembros ven los proyectos; subir,
cambiar de versión y la biblioteca de materiales dependen de los permisos del rol (talleres/permisos.py)."""
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Max, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from avance import pantalla as pantalla_de_avance
from conversor.polyboard_a_app import clave
from modulos import registro
from talleres.archivos import abrir_de_taller
from talleres.roles import con_permiso, miembro, puede

from . import probador
from .archivos import solo_nombre
from . import borrar as borrado
from .formularios import (FormBiblioteca, FormDatos, FormMaterial, FormMaterialNuevo, FormProyectoNuevo,
                          FormSinCanto, FormSubida)
from .models import GrupoDeColor, LinkCliente, Material, Original, Proyecto, Version, para_produccion
from .tareas import encolar
from .visor import url_de_link



def a_proyecto(request, proyecto, seccion=None, ancla=''):
    """A la pantalla del proyecto, en la sección `seccion` (Resumen si no se dice)."""
    destino = reverse('taller:proyectos:ver', kwargs={'taller': request.taller.slug, 'id': proyecto.pk})
    return redirect(destino + (f'?ver={seccion}' if seccion else '') + ancla)


def formulario(clase, request):
    """Formulario de subida con los campos que suman los módulos prendidos del taller."""
    form = clase(request.POST or None, request.FILES or None)
    for modulo in registro.activos():
        modulo.campos_de_subida(form)
    return form


def pantalla_de_subida(request, form, proyecto, datos=None):
    extras = [modulo.html_de_subida(form) for modulo in registro.activos()]
    return render(request, 'proyectos/subir.html', {'form': form, 'proyecto': proyecto, 'datos': datos,
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


FILTROS = [('', 'En curso'), ('produccion', 'En producción'), ('desarrollo', 'En desarrollo'),
           ('archivados', 'Archivados'), ('todos', 'Todos')]


@con_permiso('proyectos')
def lista(request, taller):
    """Buscar por nombre, cliente o número de pedido y filtrar por estado. "En curso": en producción y en desarrollo
    (sin los archivados)."""
    q = request.GET.get('q', '').strip()[:80]
    estado = request.GET.get('estado', '')
    estado = estado if estado in dict(FILTROS) else ''
    qs = Proyecto.objects.select_related('version_actual').prefetch_related('versiones')
    if estado == 'produccion':
        qs = para_produccion(qs)
    elif estado == 'desarrollo':
        qs = qs.filter(en_produccion=False, archivado_en__isnull=True)
    elif estado == 'archivados':
        qs = qs.filter(archivado_en__isnull=False).order_by('-archivado_en')
    elif estado != 'todos':
        qs = qs.filter(archivado_en__isnull=True)
    if q:
        qs = qs.filter(Q(nombre__icontains=q) | Q(cliente__icontains=q) | Q(pedido__icontains=q))
    proyectos = list(qs)
    for p in proyectos:
        p.ultima = max(p.versiones.all(), key=lambda v: v.numero, default=None)
    avances = pantalla_de_avance.de_la_lista(proyectos)
    hoy = timezone.localdate()
    for p in proyectos:
        p.avance = avances.get(p.pk)
        completo = bool(p.avance and p.avance['muebles'] and p.avance['en_el_ultimo'] == p.avance['muebles'])
        p.vencida = bool(p.entrega and p.entrega < hoy and not completo and not p.archivado_en)
    archivados = Proyecto.objects.filter(archivado_en__isnull=False).count()
    return render(request, 'proyectos/lista.html', {
        'proyectos': proyectos, 'q': q, 'estado': estado, 'filtros': FILTROS, 'archivados': archivados,
        'gestiona': puede(request, 'proyectos_gestion')})


@con_permiso('proyectos_gestion')
def nuevo(request, taller):
    form = formulario(FormProyectoNuevo, request)
    datos = FormDatos(request.POST or None, alta=True)
    if request.method == 'POST' and form.is_valid() and datos.is_valid():
        dxf, ocps = form.cleaned_data['archivos']
        with transaction.atomic():
            proyecto = datos.save(commit=False)
            proyecto.nombre = form.cleaned_data['nombre'].strip() or Path(solo_nombre(dxf.name)).stem[:150]
            proyecto.en_produccion = form.cleaned_data['en_produccion']
            proyecto.creado_por = request.user
            proyecto.save()
            crear_version(proyecto, request.user, archivos=(dxf, ocps), datos=form.cleaned_data)
        messages.success(request, f'Subiste {proyecto}. La conversión tarda unos minutos.'
                         + ('' if proyecto.en_produccion else ' Quedó en desarrollo: habilitalo para producción '
                                                               'cuando esté listo.'))
        return a_proyecto(request, proyecto)
    return pantalla_de_subida(request, form, None, datos)


SECCIONES = [('resumen', 'Resumen'), ('produccion', 'Producción'), ('cliente', 'Cliente'), ('versiones', 'Versiones')]


@con_permiso('proyectos')
def ver(request, taller, id):
    """El proyecto en cuatro secciones con íconos (`?ver=`, ficha 22): Resumen (datos, estado y avance general),
    Producción (avance por mueble y cargas), Cliente (link y probador de colores) y Versiones."""
    proyecto = get_object_or_404(Proyecto.objects.select_related('version_actual', 'archivado_por'), pk=id)
    seccion = request.GET.get('ver', 'resumen')
    seccion = seccion if seccion in dict(SECCIONES) else 'resumen'
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
                          .exclude(textura='', color='').values_list('tipo', 'clave'))
        for f in base.faltan_texturas:
            texto = f"{f['tipo']} {f['nombre']}"
            (texturas_nuevas if (f['tipo'], clave(f['nombre'])) in con_textura else faltan).append(texto)
    gestiona = puede(request, 'proyectos_gestion')
    links = list(proyecto.links.filter(anulado__isnull=True)) if gestiona else []
    for link in links:
        link.direccion = url_de_link(request, link)
    listo = bool(proyecto.version_actual and proyecto.version_actual.estado == Version.Estado.LISTO)
    avance = pantalla_de_avance.del_proyecto(proyecto) if proyecto.version_actual and seccion in (
        'resumen', 'produccion') else None
    return render(request, 'proyectos/ver.html', {
        'seccion': seccion, 'secciones': SECCIONES, 'hoy': timezone.localdate(),
        'probador': pantalla_del_probador(proyecto, gestiona) if listo and seccion == 'cliente' else None,
        'elecciones': list(proyecto.elecciones.all()[:50]),
        'proyecto': proyecto, 'versiones': versiones, 'base': base,
        'listo': bool(proyecto.version_actual and proyecto.version_actual.estado == Version.Estado.LISTO),
        'links': links, 'dias_link': VENCIMIENTOS, 'dias_por_defecto': LinkCliente.DIAS,
        'texturas_nuevas': texturas_nuevas, 'faltan': faltan,
        'en_proceso': any(v.en_proceso or any(m.en_proceso(v) for m in modulos) for v in versiones),
        'gestiona': gestiona, 'borra': puede(request, 'proyectos_borrar'), 'puede_marca': puede(request, 'marca'),
        'form_datos': FormDatos(instance=proyecto) if gestiona else None,
        'avance': avance,
    })


def pantalla_del_probador(proyecto, gestiona):
    """Grupos del probador de colores con lo que hace falta para editarlos en la pantalla del proyecto."""
    tableros = probador.tableros_de(probador.leer_cliente(proyecto.version_actual))
    grupos = list(GrupoDeColor.objects.filter(proyecto=proyecto))
    biblioteca = list(Material.objects.filter(tipo=Material.Tipo.TABLERO)) if gestiona else []
    presentes = {clave(t) for t in tableros}
    for g in grupos:
        g.sueltos = [t for t in g.tableros if clave(t) not in presentes]       # ya no están en esta versión
        g.marcados = {clave(t) for t in g.tableros}
        g.ofrecidos = set(g.opciones)
    usados = {clave(t) for g in grupos for t in g.tableros}
    return {'tableros': [(t, clave(t)) for t in tableros], 'grupos': grupos, 'biblioteca': biblioteca,
            'libres': [t for t in tableros if clave(t) not in usados]}


@require_POST
@con_permiso('proyectos_gestion')
def grupo_color(request, taller, id, grupo_id=None):
    """Crear, guardar o borrar un grupo del probador de colores."""
    proyecto = get_object_or_404(Proyecto.objects.select_related('version_actual'), pk=id)
    grupo = get_object_or_404(GrupoDeColor, pk=grupo_id, proyecto=proyecto) if grupo_id else None
    volver = a_proyecto(request, proyecto, 'cliente', '#colores')
    if grupo and request.POST.get('borrar'):
        grupo.delete()
        messages.success(request, f'Borraste el grupo {grupo.nombre}.')
        return volver
    nombre = request.POST.get('nombre', '').strip()[:60]
    presentes = {clave(t): t for t in probador.tableros_de(probador.leer_cliente(proyecto.version_actual))}
    # los tableros de versiones anteriores que el grupo ya tenía se conservan (pueden volver)
    tableros = [presentes[k] for k in dict.fromkeys(clave(t) for t in request.POST.getlist('tablero'))
                if k in presentes]
    tableros += [t for t in (grupo.tableros if grupo else []) if clave(t) not in presentes]
    try:
        pedidas = {int(x) for x in request.POST.getlist('opcion')}
    except ValueError:
        pedidas = set()
    opciones = sorted(Material.objects.filter(pk__in=pedidas, tipo=Material.Tipo.TABLERO)
                      .values_list('pk', flat=True))
    if not nombre or not tableros or not opciones:
        messages.error(request, 'El grupo necesita un nombre, al menos un tablero del proyecto y al menos un color '
                                'para ofrecer.')
        return volver
    if grupo is None:
        grupo = GrupoDeColor(proyecto=proyecto, orden=GrupoDeColor.objects.filter(proyecto=proyecto).count())
    grupo.nombre, grupo.tableros, grupo.opciones = nombre, tableros, opciones
    grupo.save()
    messages.success(request, f'Guardaste el grupo {nombre}. El cliente ya lo ve en su link.')
    return volver


@require_POST
@con_permiso('proyectos_gestion')
def datos(request, taller, id):
    proyecto = get_object_or_404(Proyecto, pk=id)
    form = FormDatos(request.POST, instance=proyecto)
    if form.is_valid():
        form.save()
        messages.success(request, 'Guardaste los datos del proyecto.')
    else:
        messages.error(request, 'Revisá los datos: ' + ' '.join(f'{form.fields[c].label}: {e}' for c, es in
                                                               form.errors.items() for e in es))
    return a_proyecto(request, proyecto)


@require_POST
@con_permiso('proyectos_gestion')
def produccion(request, taller, id):
    """Habilitar o deshabilitar el proyecto para producción (en desarrollo: el cliente lo ve en su link, pero no
    aparece en Mi puesto, el Tablero, el visor ni Tareas)."""
    proyecto = get_object_or_404(Proyecto, pk=id, archivado_en__isnull=True)
    proyecto.en_produccion = request.POST.get('en_produccion') == '1'
    proyecto.save(update_fields=['en_produccion', 'actualizado'])
    messages.success(request, 'Listo: el proyecto está en producción.' if proyecto.en_produccion else
                     'Listo: el proyecto quedó en desarrollo. Ya no aparece en Mi puesto, el Tablero, el visor ni '
                     'Tareas; el cliente lo sigue viendo en su link.')
    return a_proyecto(request, proyecto)


@require_POST
@con_permiso('proyectos_gestion')
def archivar(request, taller, id):
    proyecto = get_object_or_404(Proyecto, pk=id, archivado_en__isnull=True)
    proyecto.archivado_en, proyecto.archivado_por = timezone.now(), request.user
    proyecto.save(update_fields=['archivado_en', 'archivado_por', 'actualizado'])
    messages.success(request, f'Archivaste {proyecto}. Está en Proyectos → Archivados; desde ahí se puede '
                              'desarchivar o borrar.')
    return redirect('taller:proyectos:lista', taller=request.taller.slug)


@require_POST
@con_permiso('proyectos_gestion')
def desarchivar(request, taller, id):
    proyecto = get_object_or_404(Proyecto, pk=id, archivado_en__isnull=False)
    proyecto.archivado_en = proyecto.archivado_por = None
    proyecto.save(update_fields=['archivado_en', 'archivado_por', 'actualizado'])
    messages.success(request, f'Desarchivaste {proyecto}. Está {proyecto.get_estado_display().lower()}.')
    return a_proyecto(request, proyecto)


@require_POST
@con_permiso('proyectos_borrar')
def borrar(request, taller, id):
    """Borrar del todo un proyecto archivado: hay que escribir su nombre. No se puede deshacer."""
    proyecto = get_object_or_404(Proyecto, pk=id, archivado_en__isnull=False)
    if request.POST.get('nombre', '').strip().lower() != proyecto.nombre.strip().lower():
        messages.error(request, 'Para borrarlo, escribí el nombre del proyecto tal cual.')
        return a_proyecto(request, proyecto)
    nombre = proyecto.nombre
    borrado.borrar(proyecto)
    messages.success(request, f'Borraste {nombre} con sus versiones, su avance, sus tareas y sus fotos.')
    return redirect(reverse('taller:proyectos:lista', kwargs={'taller': request.taller.slug}) + '?estado=archivados')


@con_permiso('proyectos_gestion')
def nueva_version(request, taller, id):
    proyecto = get_object_or_404(Proyecto, pk=id)
    form = formulario(FormSubida, request)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            version = crear_version(proyecto, request.user, archivos=form.cleaned_data['archivos'],
                                    datos=form.cleaned_data)
        messages.success(request, f'Subiste la versión {version.numero}. La conversión tarda unos minutos.')
        return a_proyecto(request, proyecto, 'versiones')
    return pantalla_de_subida(request, form, proyecto)


@require_POST
@con_permiso('proyectos_gestion')
def usar_version(request, taller, id, numero):
    proyecto = get_object_or_404(Proyecto, pk=id)
    version = get_object_or_404(proyecto.versiones, numero=numero, estado=Version.Estado.LISTO)
    proyecto.version_actual = version
    proyecto.save(update_fields=['version_actual', 'actualizado'])
    messages.success(request, f'Ahora se usa la versión {version.numero}.')
    return a_proyecto(request, proyecto, 'versiones')


@require_POST
@require_POST
@con_permiso('proyectos_gestion')
def borrar_version(request, taller, id, numero):
    """Borrar una versión vieja: nunca la que está en uso ni una que se está convirtiendo."""
    proyecto = get_object_or_404(Proyecto, pk=id)
    version = get_object_or_404(proyecto.versiones, numero=numero)
    if version.pk == proyecto.version_actual_id or version.en_proceso:
        messages.error(request, f'La versión {numero} no se puede borrar: está en uso o convirtiéndose.')
    else:
        borrado.borrar_version(version)
        messages.success(request, f'Borraste la versión {numero}.')
    return a_proyecto(request, proyecto, 'versiones')


@con_permiso('proyectos_gestion')
def reconvertir(request, taller, id, numero):
    proyecto = get_object_or_404(Proyecto, pk=id)
    origen = get_object_or_404(proyecto.versiones, numero=numero)
    with transaction.atomic():
        version = crear_version(proyecto, request.user, copiar_de=origen)
    messages.success(request, f'Se está convirtiendo de nuevo como versión {version.numero}.')
    return a_proyecto(request, proyecto, 'versiones')


@con_permiso('proyectos_gestion')
def original(request, taller, id, numero, original_id):
    o = get_object_or_404(Original, pk=original_id, version__numero=numero, version__proyecto_id=id)
    if registro.oculto(o):          # la carpeta del postprocesador, con el módulo Zicar apagado
        raise Http404()
    return abrir_de_taller(request, o.archivo.name, descarga=True, nombre=o.nombre)


# pestañas de Materiales: (clave en ?ver=, título, tipo de Material, ícono)
PESTANAS_MATERIALES = [('tableros', 'Tableros', Material.Tipo.TABLERO, 'tableros'),
                       ('cantos', 'Cantos', Material.Tipo.CANTO, 'cantos')]
PESTANA_DE_TIPO = {tipo: clave for clave, _, tipo, _ in PESTANAS_MATERIALES}


def a_materiales(request, tipo):
    return redirect(reverse('taller:proyectos:materiales', kwargs={'taller': request.taller.slug})
                    + f'?ver={PESTANA_DE_TIPO[tipo]}')


@con_permiso('materiales')
def materiales(request, taller, form_nuevo=None):
    """Biblioteca del taller en dos pestañas, Tableros y Cantos: una grilla de muestras (textura o color) con buscar,
    filtro y orden en la página; cada muestra abre la ficha del material."""
    ver = PESTANA_DE_TIPO[form_nuevo.instance.tipo] if form_nuevo else request.GET.get('ver')
    ver = ver if ver in PESTANA_DE_TIPO.values() else 'tableros'
    todos = list(Material.objects.all())
    pestanas = [(c, n, icono, sum(1 for m in todos if m.tipo == t and m.falta))
                for c, n, t, icono in PESTANAS_MATERIALES]
    tipo = next(t for c, _, t, _ in PESTANAS_MATERIALES if c == ver)
    lista = sorted((m for m in todos if m.tipo == tipo), key=lambda m: m.clave)
    return render(request, 'proyectos/materiales.html', {
        'ver': ver, 'tipo': tipo, 'nombre_tipo': Material.Tipo(tipo).label.lower(), 'pestanas': pestanas,
        'lista': lista, 'faltan': sum(1 for m in lista if m.falta),
        'form_sin_canto': FormSinCanto(instance=request.taller),
        'form_nuevo': form_nuevo or FormMaterialNuevo(tipo=tipo, auto_id='nuevo_%s'),
    }, status=400 if form_nuevo else 200)


@require_POST
@con_permiso('materiales')
def nuevo_material(request, taller, tipo):
    """Agregar un tablero o canto que todavía no usa ningún proyecto (un tablero, para ofrecerlo en el probador)."""
    if tipo not in Material.Tipo.values:
        raise Http404()
    form = FormMaterialNuevo(request.POST, request.FILES, tipo=tipo, auto_id='nuevo_%s')
    if not form.is_valid():
        return materiales(request, taller=taller, form_nuevo=form)
    m = form.save()
    extra = ' Ya lo podés ofrecer en el probador de colores.' if tipo == Material.Tipo.TABLERO else ''
    messages.success(request, f'Agregaste el {m}.{extra}')
    return a_materiales(request, tipo)


@require_POST
@con_permiso('materiales')
def buscar_lisos(request, taller):
    """Suma los tableros y cantos de color liso de los proyectos ya convertidos (en la cola)."""
    from .tareas import encolar_lisos
    encolar_lisos(request.taller)
    messages.success(request, 'Se están buscando los tableros y cantos de color liso en los proyectos. En un rato '
                              'aparecen acá (recargá la página).')
    return a_materiales(request, Material.Tipo.TABLERO if request.POST.get('ver') != 'cantos' else Material.Tipo.CANTO)


@con_permiso('materiales')
def importar_biblioteca(request, taller):
    """Importar la biblioteca de Polyboard (proyectos/biblioteca.py): los .mat-boole y, después, las imágenes que
    faltan desde la carpeta Textures (la página elige cuáles y las manda de a una a importar_textura)."""
    from . import biblioteca
    enviado = request.method == 'POST'
    form = FormBiblioteca(request.POST if enviado else None, request.FILES if enviado else None)
    if request.method == 'POST' and form.is_valid():
        partes = []
        for campo, tipo in (('tableros', Material.Tipo.TABLERO), ('cantos', Material.Tipo.CANTO)):
            if form.cleaned_data.get(campo):
                r = biblioteca.importar(form.cleaned_data[campo], tipo, form.cleaned_data['reemplazar_colores'])
                partes.append(f'{campo}: {r.nuevos} nuevos, {r.cambiados} completados, {r.iguales} sin cambios')
        messages.success(request, 'Importaste la biblioteca de Polyboard (' + '; '.join(partes) + '). Ahora subí las '
                                  'imágenes que faltan desde la carpeta Textures y después tocá "Volver a convertir" '
                                  'en los proyectos.')
        return redirect('taller:proyectos:importar_biblioteca', taller=request.taller.slug)
    return render(request, 'proyectos/importar_biblioteca.html', {
        'form': form, 'faltan': biblioteca.faltan_imagenes(), 'max_mb': settings.MAX_TEXTURA_MB,
    }, status=400 if form.errors else 200)


@require_POST
@con_permiso('materiales')
def importar_textura(request, taller):
    """Una imagen de la carpeta Textures para un material (JSON). Con las mismas revisiones que la ficha."""
    from django.http import JsonResponse
    m = get_object_or_404(Material, pk=request.POST.get('id') or 0)
    if m.textura:
        return JsonResponse({'ok': True, 'ya_tenia': True})
    datos = {'nombre': m.nombre, 'veta': m.veta, 'ancho_mm': m.ancho_mm or '', 'color': m.color}
    form = FormMaterial(datos, {'textura': request.FILES.get('archivo')} if request.FILES.get('archivo') else {},
                        instance=m)
    if not request.FILES.get('archivo') or not form.is_valid():
        errores = ' '.join(e for es in form.errors.values() for e in es) or 'Falta la imagen.'
        return JsonResponse({'ok': False, 'error': errores}, status=400)
    form.save()
    return JsonResponse({'ok': True})


def probadores_con(material):
    """Proyectos cuyo probador de colores ofrece este material."""
    return sorted({g.proyecto.nombre for g in GrupoDeColor.objects.select_related('proyecto')
                   if material.pk in g.opciones})


@require_POST
@con_permiso('materiales')
def sin_canto(request, taller):
    form = FormSinCanto(request.POST, instance=request.taller)
    if form.is_valid():
        form.save()
        messages.success(request, 'Guardaste el color de los lados sin canto. En el visor ya se ve; para la realidad '
                                  'aumentada del link del cliente, tocá "Volver a convertir" en cada proyecto.')
    else:
        messages.error(request, ' '.join(e for errores in form.errors.values() for e in errores))
    return a_materiales(request, Material.Tipo.CANTO)


@con_permiso('materiales')
def material(request, taller, id):
    """Ficha de un material: todos sus datos para ver y cambiar, y Borrar."""
    m = get_object_or_404(Material, pk=id)
    tenia_textura, veta = bool(m.textura), m.veta
    enviado = request.method == 'POST'
    form = FormMaterial(request.POST if enviado else None, request.FILES if enviado else None, instance=m)
    if request.method == 'POST' and form.is_valid():
        form.save()
        if m.textura and not tenia_textura:
            messages.success(request, f'Se guardó la textura de {m}. En los proyectos que la usan, tocá '
                                      '"Volver a convertir" para verla.')
        elif m.textura and m.veta != veta:
            messages.success(request, f'Se guardó la veta de {m}. En los proyectos que la usan, tocá '
                                      '"Volver a convertir" para verla.')
        else:
            messages.success(request, f'Se guardó {m}.')
        return a_materiales(request, m.tipo)
    if request.method == 'POST':
        m.refresh_from_db()                  # la ficha muestra lo guardado, no lo que no pasó la revisión
    return render(request, 'proyectos/material.html', {
        'm': m, 'form': form, 'pestana': PESTANA_DE_TIPO[m.tipo], 'probadores': probadores_con(m),
    }, status=400 if form.errors else 200)


@require_POST
@con_permiso('materiales')
def borrar_material(request, taller, id):
    """Lo saca de la biblioteca (y su imagen). No si lo ofrece algún probador: primero hay que sacarlo de ahí."""
    m = get_object_or_404(Material, pk=id)
    probadores = probadores_con(m)
    if probadores:
        messages.error(request, f'No se puede borrar el {m}: lo ofrece el probador de colores de '
                                f'{", ".join(probadores)}. Sacalo de ahí primero.')
        return redirect('taller:proyectos:material', taller=request.taller.slug, id=m.pk)
    tipo, nombre = m.tipo, str(m)
    if m.textura:
        m.textura.delete(save=False)
    m.delete()
    messages.success(request, f'Borraste el {nombre}. Si un proyecto lo usa, vuelve a aparecer al convertirlo.')
    return a_materiales(request, tipo)


@con_permiso('materiales')
def imagen_material(request, taller, id):
    m = get_object_or_404(Material, pk=id)
    if not m.textura:
        return a_materiales(request, m.tipo)
    return abrir_de_taller(request, m.textura.name)


VENCIMIENTOS = [(30, '30 días'), (90, '90 días'), (365, 'un año'), (0, 'no vence')]


@require_POST
@con_permiso('proyectos_gestion')
def nuevo_link(request, taller, id):
    proyecto = get_object_or_404(Proyecto, pk=id)
    try:
        dias = int(request.POST.get('dias', LinkCliente.DIAS))
    except ValueError:
        dias = -1
    if dias not in dict(VENCIMIENTOS):
        messages.error(request, 'Elegí cuándo vence el link.')
        return a_proyecto(request, proyecto, 'cliente')
    LinkCliente.objects.create(proyecto=proyecto, creado_por=request.user,
                               vence=timezone.now() + timedelta(days=dias) if dias else None)
    messages.success(request, 'Listo el link para el cliente. Copialo y mandáselo.')
    return a_proyecto(request, proyecto, 'cliente')


@require_POST
@con_permiso('proyectos_gestion')
def anular_link(request, taller, id, link_id):
    link = get_object_or_404(LinkCliente, pk=link_id, proyecto_id=id, anulado__isnull=True)
    link.anulado = timezone.now()
    link.save(update_fields=['anulado'])
    messages.success(request, 'Anulaste el link: quien lo tenga ya no puede ver el proyecto.')
    return a_proyecto(request, link.proyecto, 'cliente')
