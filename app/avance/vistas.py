"""Pantallas de la ficha 13.

    /<taller>/puesto/                          modo puesto: escanear piezas, terminar muebles, cargar y entregar
    /<taller>/proyectos/<id>/cargas/nueva/     armar una carga (POST)
    /<taller>/cargas/<id>/                     lo cargado y lo que falta; "Salió a obra"
    /<taller>/procesos/                        procesos (permiso Procesos) y ubicaciones (permiso Ubicaciones)
    /<taller>/tablero/                         tablero de control de Producción
    /<taller>/etapas/                          lleva a Procesos
"""
import json

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.middleware.csrf import get_token
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.urls import reverse
from django.views.decorators.http import require_POST

from proyectos.models import Proyecto, Version, para_produccion
from talleres.limites import permite
from talleres.roles import con_permiso, miembro, puede
from trabajos.api import Rechazo

from . import acciones
from .pantalla import muebles_para_cargar
from . import entrega as entrega_
from .calculo import piezas_de
from .pasos import COLORES_AVANCE, NOMBRES_AVANCE, avance_de_proceso, pasos
from .tablero import tablero as armar_tablero
from .models import (Carga, Control, Etapa, PuntoDeControl, Ubicacion, etapas_del_taller, fijo,
                     procesos as procesos_del_taller, puntos_de_control)


def url(request, nombre, **kwargs):
    return reverse(f'taller:avance:{nombre}', kwargs={'taller': request.taller.slug, **kwargs})


@con_permiso('puesto')
def puesto(request, taller):
    proyectos = (para_produccion(Proyecto.objects.filter(version_actual__estado=Version.Estado.LISTO))
                 .exclude(version_actual__archivo_proyecto='').order_by('nombre', 'pk'))
    cargas = (Carga.objects.filter(estado=Carga.Estado.ARMANDO, proyecto__in=para_produccion(Proyecto.objects.all()))
              .select_related('proyecto'))     # las que se cargan
    base = f'/{request.taller.slug}/'
    config = {
        'csrf': get_token(request),
        'yo': str(request.user),
        'gestiona': puede(request, 'produccion_gestion'),
        'proyectos': [{'id': p.pk, 'nombre': p.nombre} for p in proyectos],
        'procesos': [{'id': e.pk, 'nombre': e.nombre, 'tipo': e.tipo, 'por_mueble': e.por_mueble}
                     for e in procesos_del_taller() if e.activa],
        'ubicaciones': [{'id': u.pk, 'nombre': u.nombre} for u in Ubicacion.objects.filter(activa=True)],
        'tareas': base + 'visor/api/trabajos/' if permite(request.taller, 'trabajos') else None,
        'urlProcesos': base + 'procesos/' if puede(request, 'procesos') or puede(request, 'ubicaciones') else None,
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
    """Alta de una carga desde el proyecto: los muebles tildados (todos, algunos o filtrados por un proceso
    completado; ver avance/elegir_muebles.html). `todo=1`: el proyecto completo."""
    proyecto = get_object_or_404(Proyecto.objects.select_related('version_actual'), pk=id)
    muebles = request.POST.getlist('mueble') if request.POST.get('todo') != '1' else []
    try:
        if request.POST.get('todo') != '1' and not muebles:
            raise Rechazo(400, 'Elegí al menos un mueble.')
        c = acciones.crear_carga(request.user, proyecto, muebles)
    except Rechazo as e:
        messages.error(request, e.error)
        return redirect(reverse('taller:proyectos:ver', kwargs={'taller': taller, 'id': id}) + '?ver=produccion#avance')
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
    datos = acciones.carga_a_dic(c)
    return render(request, 'avance/carga.html', {
        'carga': c, 'datos': datos, 'error': error, 'gestiona': puede(request, 'produccion_gestion'), 'muebles': muebles_de_la_carga(datos),
        'con_instalacion': fijo(Etapa.Tipo.INSTALACION) is not None,
        'puesto': url(request, 'puesto') + f'?c={c.pk}',
    }, status=400 if error else 200)


def muebles_de_la_carga(datos):
    """Por mueble de la carga: bultos, cuántos van en esta, entregados, en otra carga, cuántos faltan y su estado
    (`completo`, `faltan` o `sin_terminar`)."""
    salida = []
    for m in datos['muebles']:
        bs = [b for b in datos['bultos'] if b['mueble'] == m]
        if m in datos['sin_terminar']:
            salida.append({'nombre': m, 'bultos': 0, 'en_esta': 0, 'entregados': 0, 'otra': 0, 'faltan': 0,
                           'estado': 'sin_terminar'})
            continue
        en_esta = sum(1 for b in bs if b['en_esta'])
        otra = sum(1 for b in bs if not b['en_esta'] and b['estado'] != 'embalado')
        faltan = len(bs) - en_esta - otra
        salida.append({'nombre': m, 'bultos': len(bs), 'en_esta': en_esta, 'otra': otra, 'faltan': faltan,
                       'entregados': sum(1 for b in bs if b['en_esta'] and b['estado'] == 'entregado'),
                       'estado': 'faltan' if faltan else 'completo'})
    return salida


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
            # a continuación de los del taller (no de los fijos); después se arrastra a donde vaya
            propios = [e for e in lista if not getattr(e, 'fijo', False)] or lista
            modelo.objects.create(nombre=texto, orden=max((e.orden for e in propios), default=0) + 1, **extra)
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
        e = next((e for e in lista if str(e.pk) == accion.rsplit('-', 1)[1] and not getattr(e, 'fijo', False)), None)
        usada = e is not None and (e.marcas.exists() if modelo is Etapa else e.ubicados.exists()
                                   if modelo is Ubicacion else e.pk in usos_de_puntos())
        if e is not None and not usada:
            e.delete()
        elif e is not None:
            messages.error(request, f'{e.nombre} ya se usó: apagala en vez de borrarla.')
    elif modelo is Etapa and accion.startswith(f'vaciar-{nombre}-'):
        # borrar un proceso del taller ya usado, con todas sus marcas (para probar; pide confirmación en la pantalla)
        e = next((e for e in lista if str(e.pk) == accion.rsplit('-', 1)[1] and not e.fijo), None)
        if e is not None:
            with transaction.atomic():
                n = e.marcas.count()
                e.marcas.all().delete()
                e.delete()
            messages.success(request, f'Se borró {e.nombre} con sus {n} marca{"s" if n != 1 else ""}.')


@con_permiso('procesos', 'ubicaciones')
def procesos(request, taller):
    """Procesos de Producción: los procesos (los del taller y los fijos) y los puntos del control de calidad (solo el
    permiso Procesos), y las ubicaciones del taller (permiso Ubicaciones). Los fijos se renombran y se apagan; no se mueven ni se
    borran."""
    dueno = puede(request, 'procesos')            # procesos y puntos de control; si no, solo ubicaciones
    if request.method == 'POST':
        accion = request.POST.get('accion', '')
        if accion.endswith('-etapas') or '-etapas-' in accion:
            if not dueno:
                raise PermissionDenied('Tu rol no puede cambiar los procesos.')
            todos = procesos_del_taller()
            editar_lista(request, Etapa, todos, 'etapas')
            if accion == 'guardar-etapas':
                if not any(e.activa for e in procesos_del_taller()):
                    messages.error(request, 'Dejá al menos un proceso prendido.')
                    e = next(e for e in todos if e.tipo == Etapa.Tipo.ARMADO)
                    e.activa = True
                    e.save(update_fields=['activa'])
        elif accion.endswith('-puntos') or '-puntos-' in accion:
            if not dueno:
                raise PermissionDenied('Tu rol no puede cambiar el control de calidad.')
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
        'del_taller': etapas or [],
        'control_prendido': any(e.tipo == Etapa.Tipo.CONTROL and e.activa for e in etapas or [])})


@con_permiso('tablero')
def tablero(request, taller):
    ver_terminados = request.GET.get('terminados') == '1'
    return render(request, 'avance/tablero.html', {**armar_tablero(ver_terminados), 'ver_terminados': ver_terminados})


@miembro
def entrega(request, taller, id):
    """Lista del proyecto (ficha 18): cada mueble con sus pasos, del armado a la instalación. Con `?proceso=<id>`
    (ficha 20: el botón Lista de Mi puesto), el avance de ese proceso: qué muebles lo cumplieron, cuáles van a medias
    y cuáles faltan. Se actualiza sola (`?filas=1` devuelve solo las filas). Con el permiso Corregir producción se marca instalado o
    lo deshacen desde acá."""
    proyecto = get_object_or_404(Proyecto.objects.select_related('version_actual'), pk=id)
    gestiona = puede(request, 'produccion_gestion')
    if request.method == 'POST':
        if not gestiona:
            raise PermissionDenied('Tu rol no puede marcar ni deshacer instalaciones desde acá.')
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
    prendidos = [e for e in procesos_del_taller() if e.activa]
    elegido = next((e for e in prendidos if str(e.pk) == request.GET.get('proceso')), None)
    av = avance_de_proceso(proyecto, elegido, piezas) if elegido else None
    colores, nombres = {k: c for k, _, c in d['pasos']}, {k: n for k, n, _ in d['pasos']}
    contexto = {
        'proyecto': proyecto, 'gestiona': gestiona,
        'muebles': [dict(m, nombre=n, ancla=slugify(n), color=colores[m['paso']], paso_nombre=nombres[m['paso']],
                         av=dict(av['muebles'][n], color=COLORES_AVANCE[av['muebles'][n]['estado']],
                                 nombre=NOMBRES_AVANCE[av['muebles'][n]['estado']]) if av else None)
                    for n, m in d['muebles'].items()],
        'procesos': prendidos, 'elegido': elegido,
        'totales_avance': [{'clave': k, 'nombre': NOMBRES_AVANCE[k], 'color': c, 'n': av['totales'][k],
                            'pct': f"{av['totales'][k] * 100 / total:.2f}"}
                           for k, c in COLORES_AVANCE.items() if k != 'obs' or av['totales'][k]] if av else [],
        'pasos': [{'clave': k, 'nombre': nombre_, 'color': c, 'n': d['totales'][k],
                   'pct': f"{d['totales'][k] * 100 / total:.2f}"}       # texto con punto: va a CSS
                  for k, nombre_, c in d['pasos']],
        'con_control': d['con_control'], 'con_carga': 'cargado' in colores, 'con_embalaje': 'embalado' in colores,
        'con_instalacion': 'instalado' in colores, 'con_armado': 'armado' in colores,
        'visor': reverse('taller:proyectos:visor', kwargs={'taller': taller}) + f'?p={proyecto.pk}'
                 + (f'&avance={elegido.pk}' if elegido else ''),
    }
    plantilla = 'avance/entrega_filas.html' if request.GET.get('filas') == '1' else 'avance/entrega.html'
    return render(request, plantilla, contexto)


@miembro
def modificar_carga(request, taller, id):
    """Modificación de una carga que se está cargando: sus muebles."""
    c = get_object_or_404(Carga.objects.select_related('proyecto__version_actual'), pk=id)
    if request.method == 'POST':
        try:
            acciones.modificar_carga(request.user, c, request.POST.getlist('mueble'))
            messages.success(request, 'Listo: la carga quedó con esos muebles.')
            return redirect(url(request, 'carga', id=c.pk))
        except Rechazo as e:
            messages.error(request, e.error)
    elegibles, prendidos = muebles_para_cargar(c.proyecto)
    return render(request, 'avance/carga_modificar.html', {
        'carga': c, 'elegibles': elegibles, 'procesos': prendidos, 'marcados': acciones.muebles_de(c)})


@require_POST
@con_permiso('produccion_gestion')
def anular_carga(request, taller, id):
    """Baja de una carga que no salió: los bultos cargados vuelven a embalados."""
    c = get_object_or_404(Carga.objects.select_related('proyecto'), pk=id)
    try:
        acciones.anular_carga(request.user, c)
        messages.success(request, f'Carga {c.pk} anulada: sus bultos quedaron libres para otra carga.')
    except Rechazo as e:
        messages.error(request, e.error)
        return redirect(url(request, 'carga', id=c.pk))
    return redirect(reverse('taller:proyectos:ver', kwargs={'taller': taller, 'id': c.proyecto_id})
                    + '?ver=produccion#cargas')


@con_permiso('procesos', 'ubicaciones')
def etapas(request, taller):
    """La pantalla vieja de Etapas: ahora está en Procesos."""
    return redirect(url(request, 'procesos'))
