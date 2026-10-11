"""Pantallas de la ficha 13.

    /<taller>/puesto/                          modo puesto: escanear piezas, terminar muebles, cargar y entregar
    /<taller>/proyectos/<id>/cargas/nueva/     armar una carga (POST)
    /<taller>/cargas/<id>/                     lo cargado y lo que falta; "Salió a obra"
    /<taller>/etapas/                          las etapas del taller (solo el dueño)
"""
import json

from django.contrib import messages
from django.db.models import Count, Q
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from proyectos.models import Proyecto, Version
from talleres.roles import Rol, con_rol, miembro
from trabajos.api import Rechazo

from . import acciones
from .models import Carga, Etapa, etapas_del_taller


def url(request, nombre, **kwargs):
    return reverse(f'taller:avance:{nombre}', kwargs={'taller': request.taller.slug, **kwargs})


@miembro
def puesto(request, taller):
    proyectos = (Proyecto.objects.filter(version_actual__estado=Version.Estado.LISTO)
                 .exclude(version_actual__archivo_proyecto='').order_by('nombre', 'pk'))
    cargas = Carga.objects.exclude(estado=Carga.Estado.ENTREGADA).select_related('proyecto')
    base = f'/{request.taller.slug}/'
    config = {
        'csrf': get_token(request),
        'yo': str(request.user),
        'gestiona': request.membresia.rol in (Rol.DUENO, Rol.OFICINA),
        'proyectos': [{'id': p.pk, 'nombre': p.nombre} for p in proyectos],
        'etapas': [{'id': e.pk, 'nombre': e.nombre} for e in etapas_del_taller() if e.activa],
        'cargas': [{'id': c.pk, 'proyecto': c.proyecto_id, 'nombre': f'{c.proyecto.nombre} · carga {c.pk}',
                    'estado': c.estado} for c in cargas],
        'api': base + 'puesto/api/',
        'pdf': base + 'visor/api/etiquetas/pdf',
        'carga': base + 'cargas/{id}/',
        'visor': base + 'visor/',
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
        'puesto': url(request, 'puesto') + f'?c={c.pk}',
    }, status=400 if error else 200)


@con_rol(Rol.DUENO)
def etapas(request, taller):
    lista = etapas_del_taller()
    if request.method == 'POST':
        accion = request.POST.get('accion', '')
        if accion == 'agregar':
            nombre = request.POST.get('nombre', '').strip()[:40]
            if nombre:
                Etapa.objects.create(nombre=nombre, orden=max((e.orden for e in lista), default=0) + 1)
        elif accion == 'guardar':
            for e in lista:
                nombre = request.POST.get(f'nombre-{e.pk}', '').strip()[:40]
                e.nombre = nombre or e.nombre
                e.activa = request.POST.get(f'activa-{e.pk}') == '1'
                e.save(update_fields=['nombre', 'activa'])
            if not any(e.activa for e in lista):
                messages.error(request, 'Dejá al menos una etapa prendida.')
                lista[-1].activa = True
                lista[-1].save(update_fields=['activa'])
        elif accion.startswith(('subir-', 'bajar-')):
            i = next((i for i, e in enumerate(lista) if str(e.pk) == accion[6:]), None)
            j = None if i is None else i - 1 if accion.startswith('subir-') else i + 1
            if i is not None and 0 <= j < len(lista):
                lista[i], lista[j] = lista[j], lista[i]
                for n, e in enumerate(lista, 1):
                    e.orden = n
                    e.save(update_fields=['orden'])
        elif accion.startswith('borrar-'):
            e = next((e for e in lista if str(e.pk) == accion[7:]), None)
            if e is not None and not e.marcas.exists() and len(lista) > 1:
                e.delete()
            elif e is not None:
                messages.error(request, f'{e.nombre} ya tiene piezas marcadas: apagala en vez de borrarla.')
        return redirect(url(request, 'etapas'))
    lista = list(Etapa.objects.annotate(usadas=Count('marcas', filter=Q(marcas__deshecha_en__isnull=True))))
    return render(request, 'avance/etapas.html', {'etapas': lista,
                                                  'armado': next((e for e in reversed(lista) if e.activa), None)})
