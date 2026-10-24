"""Pantallas de la ficha 13.

    /<taller>/puesto/                          modo puesto: escanear piezas, terminar muebles, cargar y entregar
    /<taller>/proyectos/<id>/cargas/nueva/     armar una carga (POST)
    /<taller>/cargas/<id>/                     lo cargado y lo que falta; "Salió a obra"
    /<taller>/procesos/                        etapas (solo el dueño) y ubicaciones (dueño y oficina)
    /<taller>/tablero/                         tablero de control de Producción
    /<taller>/etapas/                          lleva a Procesos
"""
import json

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.middleware.csrf import get_token
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.urls import reverse
from django.views.decorators.http import require_POST

from proyectos.models import Proyecto, Version
from talleres.limites import permite
from talleres.roles import Rol, con_rol, miembro
from trabajos.api import Rechazo

from . import acciones
from . import entrega as entrega_
from .calculo import piezas_de
from .pasos import pasos
from .tablero import tablero as armar_tablero
from .models import (Carga, Control, Etapa, PuntoDeControl, Ubicacion, etapas_del_taller, fijo,
                     procesos as procesos_del_taller, puntos_de_control)


def url(request, nombre, **kwargs):
    return reverse(f'taller:avance:{nombre}', kwargs={'taller': request.taller.slug, **kwargs})


@miembro
def puesto(request, taller):
    proyectos = (Proyecto.objects.filter(version_actual__estado=Version.Estado.LISTO)
                 .exclude(version_actual__archivo_proyecto='').order_by('nombre', 'pk'))
    cargas = Carga.objects.filter(estado=Carga.Estado.ARMANDO).select_related('proyecto')     # las que se cargan
    base = f'/{request.taller.slug}/'
    config = {
        'csrf': get_token(request),
        'yo': str(request.user),
        'gestiona': request.membresia.rol in (Rol.DUENO, Rol.OFICINA),
        'proyectos': [{'id': p.pk, 'nombre': p.nombre} for p in proyectos],
        'procesos': [{'id': e.pk, 'nombre': e.nombre, 'tipo': e.tipo, 'por_mueble': e.por_mueble}
                     for e in procesos_del_taller() if e.activa],
        'ubicaciones': [{'id': u.pk, 'nombre': u.nombre} for u in Ubicacion.objects.filter(activa=True)],
        'tareas': base + 'visor/api/trabajos/' if permite(request.taller, 'trabajos') else None,
        'urlProcesos': base + 'procesos/' if request.membresia.rol in (Rol.DUENO, Rol.OFICINA) else None,
        'cargas': [{'id': c.pk, 'proyecto': c.proyecto_id, 'nombre': f'{c.proyecto.nombre} · carga {c.pk}',
                    'estado': c.estado} for c in cargas],
        'api': base + 'puesto/api/',
        'pdf': base + 'visor/api/etiquetas/pdf',
        'carga': base + 'cargas/{id}/',
        'visor': base + 'visor/',
        'entrega': base + 'proyectos/{id}/entrega/',
    }
    return render(request, 'avance/puesto.html', {'config': json.dumps(config, ensure_ascii=False).replace('<', '\\u003c')})


@require_POST
@miembro
def nueva_carga(request, taller, id):
    proyecto = get_object_or_404(Proyecto.objects.select_related('version_actual'), pk=id)
    muebles = request.POST.getlist('mueble') if request.POST.get('todo') != '1' else []
    try:
        if request.POST.get('todo') != '1' and not muebles:
            raise Rechazo(400, 'Elegí el proyecto completo o algunos muebles.')
        c = acciones.crear_carga(request.user, proyecto, muebles)
    except Rechazo as e:
        messages.error(request, e.error)
        return redirect(reverse('taller:proyectos:ver', kwargs={'taller': taller, 'id': id}) + '#avance')
    return redirect(url(request, 'carga', id=c.pk))


@miembro
def carga(request, taller, id):
    c = get_object_or_404(Carga.objects.select_related('proyecto__version_actual', 'creada_por', 'salio_por',
                                                       'entregada_por'), pk=id)
    error = None
    if request.method == 'POST':
        try:
            acciones.salir(request.user, c, request.POST.get('motivo', ''))
            messages.success(request, 'Listo: la carga salió a obra.')
            return redirect(url(request, 'carga', id=c.pk))
        except Rechazo as e:
            error = e.error
    return render(request, 'avance/carga.html', {
        'carga': c, 'datos': acciones.carga_a_dic(c), 'error': error,
        'con_instalacion': fijo(Etapa.Tipo.INSTALACION) is not None,
        'puesto': url(request, 'puesto') + f'?c={c.pk}',
    }, status=400 if error else 200)


def usos_de_puntos():
    """Cuántos controles usaron cada punto (los resultados guardan el id del punto)."""
    usos = {}
    for resultados in Control.objects.values_list('resultados', flat=True):
        for r in resultados:
            usos[r.get('punto')] = usos.get(r.get('punto'), 0) + 1
    return usos


def editar_lista(request, modelo, lista, nombre, sin_ninguna=None):
    """Lo que manda la tabla de Procesos para una lista ordenada (etapas o ubicaciones): agregar, guardar nombres,
    tildes y el orden en que quedaron las filas, o borrar una que nunca se usó. `nombre` es el prefijo de los
    campos y de las acciones; `sin_ninguna`, el aviso si no puede quedar ninguna prendida."""
    accion = request.POST.get('accion', '')
    if accion == f'agregar-{nombre}':
        texto = request.POST.get('nombre', '').strip()[:40]
        if texto:
            extra = {'por_mueble': request.POST.get('por') == 'mueble'} if modelo is Etapa else {}
            modelo.objects.create(nombre=texto, orden=max((e.orden for e in lista), default=0) + 1, **extra)
    elif accion == f'guardar-{nombre}':
        for e in lista:
            texto = request.POST.get(f'nombre-{e.pk}', '').strip()[:40]
            e.nombre = texto or e.nombre
            e.activa = request.POST.get(f'activa-{e.pk}') == '1'
            campos = ['nombre', 'activa']
            if modelo is Etapa and f'por-{e.pk}' in request.POST:
                e.por_mueble = request.POST[f'por-{e.pk}'] == 'mueble'
                campos.append('por_mueble')
            e.save(update_fields=campos)
        if sin_ninguna and lista and not any(e.activa for e in lista):
            messages.error(request, sin_ninguna)
            lista[-1].activa = True
            lista[-1].save(update_fields=['activa'])
        # el orden en que quedaron las filas al arrastrarlas (ids separados por coma); las que falten, al final
        pedido = [i for i in request.POST.get('orden', '').split(',') if i.isdigit()]
        if pedido:
            lugar = {int(i): n for n, i in enumerate(pedido)}
            lista.sort(key=lambda e: lugar.get(e.pk, len(lugar)))
            for n, e in enumerate(lista, 1):
                if e.orden != n:
                    e.orden = n
                    e.save(update_fields=['orden'])
    elif accion.startswith(f'borrar-{nombre}-'):
        e = next((e for e in lista if str(e.pk) == accion.rsplit('-', 1)[1]), None)
        usada = e is not None and (e.marcas.exists() if modelo is Etapa else e.ubicados.exists()
                                   if modelo is Ubicacion else e.pk in usos_de_puntos())
        if e is not None and not usada:
            e.delete()
        elif e is not None:
            messages.error(request, f'{e.nombre} ya se usó: apagala en vez de borrarla.')


@con_rol(Rol.DUENO, Rol.OFICINA)
def procesos(request, taller):
    """Procesos de Producción: los procesos (los del taller y los fijos) y los puntos del control de calidad (solo el
    dueño), y las ubicaciones del taller (dueño y oficina). Los fijos se renombran y se apagan; no se mueven ni se
    borran."""
    dueno = request.membresia.rol == Rol.DUENO
    if request.method == 'POST':
        accion = request.POST.get('accion', '')
        if accion.endswith('-etapas') or '-etapas-' in accion:
            if not dueno:
                raise PermissionDenied('Las etapas las cambia el dueño.')
            todos = procesos_del_taller()
            editar_lista(request, Etapa, [e for e in todos if not e.fijo], 'etapas')
            if accion == 'guardar-etapas':
                for e in (e for e in todos if e.fijo):
                    e.nombre = request.POST.get(f'nombre-{e.pk}', '').strip()[:40] or e.nombre
                    e.activa = request.POST.get(f'activa-{e.pk}') == '1'
                    e.save(update_fields=['nombre', 'activa'])
                if not any(e.activa for e in procesos_del_taller()):
                    messages.error(request, 'Dejá al menos un proceso prendido.')
                    e = next(e for e in todos if e.tipo == Etapa.Tipo.ARMADO)
                    e.activa = True
                    e.save(update_fields=['activa'])
        elif accion.endswith('-puntos') or '-puntos-' in accion:
            if not dueno:
                raise PermissionDenied('El control de calidad lo cambia el dueño.')
            editar_lista(request, PuntoDeControl, puntos_de_control(), 'puntos')
        else:
            editar_lista(request, Ubicacion, list(Ubicacion.objects.all()), 'ubicaciones')
        return redirect(url(request, 'procesos'))
    etapas = puntos = None
    if dueno:
        usos = usos_de_puntos()
        puntos = puntos_de_control()
        for x in puntos:
            x.usadas = usos.get(x.pk, 0)
        usadas = dict(Etapa.objects.annotate(n=Count('marcas', filter=Q(marcas__deshecha_en__isnull=True)))
                      .values_list('pk', 'n'))
        etapas = procesos_del_taller()
        for e in etapas:
            e.usadas = usadas.get(e.pk, 0)
    ubicaciones = list(Ubicacion.objects.annotate(usadas=Count('ubicados')).order_by('orden', 'pk'))
    return render(request, 'avance/procesos.html', {
        'etapas': etapas, 'ubicaciones': ubicaciones, 'puntos': puntos,
        'del_taller': [e for e in etapas or [] if not e.fijo], 'fijos': [e for e in etapas or [] if e.fijo],
        'control_prendido': any(e.tipo == Etapa.Tipo.CONTROL and e.activa for e in etapas or [])})


@miembro
def tablero(request, taller):
    ver_terminados = request.GET.get('terminados') == '1'
    return render(request, 'avance/tablero.html', {**armar_tablero(ver_terminados), 'ver_terminados': ver_terminados})


@miembro
def entrega(request, taller, id):
    """Lista de entrega del proyecto (ficha 18): cada mueble con sus pasos, del armado a la instalación. Se actualiza
    sola (`?filas=1` devuelve solo las filas). El dueño y la oficina marcan instalado o lo deshacen desde acá."""
    proyecto = get_object_or_404(Proyecto.objects.select_related('version_actual'), pk=id)
    gestiona = request.membresia.rol in (Rol.DUENO, Rol.OFICINA)
    if request.method == 'POST':
        if not gestiona:
            raise PermissionDenied('Marcar o deshacer una instalación desde acá es del dueño o la oficina.')
        mueble = request.POST.get('mueble', '')
        try:
            if request.POST.get('accion') == 'desinstalar':
                entrega_.desinstalar(request.user, proyecto.pk, mueble)
                messages.success(request, f'{mueble}: se deshizo la instalación.')
            else:
                entrega_.instalar(request.user, proyecto.pk, mueble, request.POST.get('nota', ''),
                                  request.POST.get('motivo', ''))
                messages.success(request, f'{mueble}: instalado.')
        except Rechazo as e:
            messages.error(request, f'{mueble}: {e.error}')
        return redirect(url(request, 'entrega', id=proyecto.pk) + '#' + slugify(mueble))
    piezas = piezas_de(proyecto) if proyecto.version_actual else []
    if not piezas:
        raise Http404()
    d = pasos(proyecto, piezas)
    total = len(d['muebles']) or 1
    colores, nombres = {k: c for k, _, c in d['pasos']}, {k: n for k, n, _ in d['pasos']}
    contexto = {
        'proyecto': proyecto, 'gestiona': gestiona,
        'muebles': [dict(m, nombre=n, ancla=slugify(n), color=colores[m['paso']], paso_nombre=nombres[m['paso']])
                    for n, m in d['muebles'].items()],
        'pasos': [{'clave': k, 'nombre': nombre_, 'color': c, 'n': d['totales'][k],
                   'pct': f"{d['totales'][k] * 100 / total:.2f}"}       # texto con punto: va a CSS
                  for k, nombre_, c in d['pasos']],
        'con_control': d['con_control'], 'con_carga': 'cargado' in colores, 'con_embalaje': 'embalado' in colores,
        'con_instalacion': 'instalado' in colores, 'con_armado': 'armado' in colores,
        'visor': reverse('taller:proyectos:visor', kwargs={'taller': taller}) + f'?p={proyecto.pk}&entrega=1',
    }
    plantilla = 'avance/entrega_filas.html' if request.GET.get('filas') == '1' else 'avance/entrega.html'
    return render(request, plantilla, contexto)


@con_rol(Rol.DUENO, Rol.OFICINA)
def etapas(request, taller):
    """La pantalla vieja de Etapas: ahora está en Procesos."""
    return redirect(url(request, 'procesos'))
