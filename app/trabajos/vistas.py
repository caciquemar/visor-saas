"""Pantalla "Trabajos" del taller: los trabajos de todos los proyectos en una lista, con filtros, el botón ✓ para pasar
al estado siguiente y el salto al visor con el trabajo abierto. Pedido de Martín (2026-10-07), agregado a la ficha 05.
Los datos y permisos son los de trabajos/api.py: acá no se filtra por taller a mano (lo hace DatoDeTaller)."""
from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from proyectos.models import Proyecto
from talleres.limites import MENSAJES, permite
from talleres.models import Membresia
from talleres.roles import Rol, miembro

from .models import Trabajo

# armadores e instaladores entran viendo lo suyo; dueño y oficina, todo
CON_PARA_MI = (Rol.ARMADOR, Rol.INSTALADOR)
ORDEN = {'vencido': 0, 'pendiente': 1, 'en proceso': 2, 'hecho': 3, 'instalado': 4}


def filtros_de(request):
    """Los filtros del pedido. Sin ninguno, el que corresponde al rol."""
    g = request.GET
    f = {'para': g.get('para', 'mi' if not g and request.membresia.rol in CON_PARA_MI else ''),
         'proyecto': g.get('proyecto', ''), 'estado': g.get('estado', ''), 'instalados': g.get('instalados') == '1'}
    for clave in ('para', 'proyecto'):
        if f[clave] not in ('', 'mi', 'nadie') and not f[clave].isdigit():
            f[clave] = ''
    if f['estado'] not in ('', 'vencido', *Trabajo.Estado.values):
        f['estado'] = ''
    return f


@miembro
def lista(request, taller):
    f = filtros_de(request)
    qs = (Trabajo.objects.select_related('proyecto', 'autor', 'asignado')
          .annotate(n_fotos=Count('fotos')))
    if f['para'] == 'mi':
        qs = qs.filter(asignado=request.user)
    elif f['para'] == 'nadie':
        qs = qs.filter(asignado__isnull=True)
    elif f['para']:
        qs = qs.filter(asignado_id=int(f['para']))
    if f['proyecto']:
        qs = qs.filter(proyecto_id=int(f['proyecto']))
    if f['estado'] and f['estado'] != 'vencido':
        qs = qs.filter(estado=f['estado'])
    elif not f['instalados']:
        qs = qs.exclude(estado=Trabajo.Estado.INSTALADO)

    hoy = timezone.localdate()
    trabajos = []
    for t in qs:
        t.es_vencido = t.vencido(hoy)
        if f['estado'] == 'vencido' and not t.es_vencido:
            continue
        t.grupo = 'vencido' if t.es_vencido else t.estado
        t.proximo = t.siguiente()
        trabajos.append(t)
    # vencidos primero; después por estado, fecha límite (las que no tienen, al final) y el más nuevo arriba
    trabajos.sort(key=lambda t: (ORDEN[t.grupo], t.limite is None, t.limite or hoy, -t.pk))

    equipo = (Membresia.objects.filter(activa=True).select_related('usuario'))
    return render(request, 'trabajos/lista.html', {
        'trabajos': trabajos, 'f': f, 'hoy': hoy,
        'equipo': sorted((m.usuario for m in equipo), key=lambda u: str(u).lower()),
        'proyectos': Proyecto.objects.filter(trabajos__isnull=False).distinct().order_by('nombre'),
        'estados': Trabajo.Estado.choices,
        'puede_cambiar': permite(request.taller, 'trabajos'),
        'volver': request.get_full_path(),
    })


@require_POST
@miembro
def avanzar(request, taller, id):
    """El ✓ de la lista: pasa al estado siguiente (cualquier miembro puede, como en el visor)."""
    volver = request.POST.get('volver', '')
    if not volver.startswith(f'/{request.taller.slug}/trabajos/') or '//' in volver:
        volver = f'/{request.taller.slug}/trabajos/'
    if not permite(request.taller, 'trabajos'):
        messages.error(request, MENSAJES['trabajos'])
        return redirect(volver)
    with transaction.atomic():
        t = get_object_or_404(Trabajo.objects.select_for_update(), pk=id)
        # se manda el estado que se vio en la pantalla: si otro ya lo cambió, no se avanza dos veces
        if request.POST.get('desde') == t.estado and t.siguiente():
            t.pasar_a(t.siguiente(), request.user)
            t.save()
            messages.success(request, f'«{t.texto[:60]}» pasó a {t.get_estado_display().lower()}.')
        else:
            messages.error(request, 'Ese trabajo ya había cambiado: fijate cómo está ahora.')
    return redirect(volver)
