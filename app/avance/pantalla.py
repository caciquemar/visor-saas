"""Lo que muestran del avance la lista de proyectos y la pantalla del proyecto."""
from proyectos.models import Version

from .calculo import avance, piezas_de, piezas_nuevas
from .models import Bulto, Carga, FinDeMueble, Marca
from .pasos import pasos


def del_proyecto(proyecto):
    """Para proyectos/ver.html: por mueble el % y cada etapa, si está terminado y sus bultos; las cargas; las piezas
    nuevas de la versión. None si el proyecto no tiene versión lista."""
    try:
        piezas = piezas_de(proyecto)
    except FileNotFoundError:
        return None
    if not piezas:
        return None
    a = avance(proyecto, piezas)
    entrega = pasos(proyecto, piezas, a)['muebles']
    bultos = {}
    for b in Bulto.objects.filter(proyecto=proyecto, fin__anulado_en__isnull=True).order_by('numero'):
        bultos.setdefault(b.mueble, []).append(b)
    muebles = []
    for nombre, m in sorted(a['muebles'].items(), key=lambda kv: kv[0].lower()):
        muebles.append({'nombre': nombre, 'pct': m['pct'], 'piezas': m['piezas'],
                        'etapas': [(e.nombre, m['por_etapa'][e.pk]) for e in a['etapas']], 'fin': m['fin'],
                        'bultos': bultos.get(nombre, []), 'control': entrega[nombre]['control'],
                        'instalacion': entrega[nombre]['instalacion']})
    return {
        'etapas': a['etapas'], 'total': a['total'], 'muebles': muebles, 'sueltas': a['sueltas'],
        'nuevas': piezas_nuevas(proyecto, piezas),
        'cargas': list(Carga.objects.filter(proyecto=proyecto).select_related('creada_por')),
    }


def de_la_lista(proyectos):
    """{id del proyecto: % total} para la lista, solo de los proyectos que ya tienen avance (los demás no se leen)."""
    con_avance = (set(Marca.objects.filter(deshecha_en__isnull=True).values_list('proyecto_id', flat=True))
                  | set(FinDeMueble.objects.filter(anulado_en__isnull=True).values_list('proyecto_id', flat=True)))
    salida = {}
    for p in proyectos:
        if p.pk in con_avance and p.version_actual and p.version_actual.estado == Version.Estado.LISTO:
            try:
                a = avance(p)
            except FileNotFoundError:
                continue
            salida[p.pk] = {'pct': a['total']['pct'], 'terminados': a['total']['terminados'],
                            'muebles': len(a['muebles'])}
    return salida
