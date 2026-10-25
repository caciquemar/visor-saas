"""Lo que muestran del avance la lista de proyectos y la pantalla del proyecto."""
from proyectos.models import Version

from .calculo import avance, piezas_de, piezas_nuevas
from .models import Bulto, Carga, FinDeMueble, Marca
from .pasos import pasos, pasos_activos


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
    def corta(d):                 # '2026-10-24 15:46' (como lo da la API) → '24/10 15:46'
        if d and d.get('cuando'):
            fecha, _, h = d['cuando'].partition(' ')
            _, mes, dia = fecha.split('-')
            d = {**d, 'cuando': f'{int(dia)}/{int(mes)} {h}'}
        return d

    nombres_de_pasos = {k: n for k, n, _ in pasos_activos()}
    nombres_de_pasos.setdefault('sin_armar', 'Sin armar')
    muebles = []
    for nombre, m in sorted(a['muebles'].items(), key=lambda kv: kv[0].lower()):
        muebles.append({'nombre': nombre, 'pct': m['pct'], 'piezas': m['piezas'],
                        'etapas': [(e.nombre, m['por_etapa'][e.pk]) for e in a['etapas']], 'fin': m['fin'],
                        'bultos': bultos.get(nombre, []), 'control': corta(entrega[nombre]['control']),
                        'instalacion': corta(entrega[nombre]['instalacion']), 'carga': entrega[nombre]['bultos'],
                        'paso': nombres_de_pasos.get(entrega[nombre]['paso'], ''),
                        'anotaciones': entrega[nombre]['anotaciones']})
    return {
        'etapas': a['etapas'], 'total': a['total'], 'muebles': muebles, 'sueltas': a['sueltas'],
        'pct_str': f"{a['total']['pct']:.2f}",
        'nuevas': piezas_nuevas(proyecto, piezas),
        'cargas': cargas_con_resumen(proyecto),
        'elegibles': muebles_para_cargar(proyecto, piezas),
    }


def de_la_lista(proyectos):
    """{id del proyecto: % total, terminados, muebles y cuántos llegaron al último paso} para la lista, solo de los
    proyectos que ya tienen avance (los demás no se leen)."""
    con_avance = (set(Marca.objects.filter(deshecha_en__isnull=True).values_list('proyecto_id', flat=True))
                  | set(FinDeMueble.objects.filter(anulado_en__isnull=True).values_list('proyecto_id', flat=True)))
    salida, ultimo = {}, None
    for p in proyectos:
        if p.pk in con_avance and p.version_actual and p.version_actual.estado == Version.Estado.LISTO:
            try:
                piezas = piezas_de(p)
                a = avance(p, piezas)
            except FileNotFoundError:
                continue
            ultimo = ultimo or pasos_activos()[-1]
            del_ultimo = sum(1 for m in pasos(p, piezas, a)['muebles'].values() if m['paso'] == ultimo[0])
            salida[p.pk] = {'pct': a['total']['pct'], 'terminados': a['total']['terminados'],
                            'muebles': len(a['muebles']), 'ultimo': ultimo[1].lower(), 'en_el_ultimo': del_ultimo,
                            'pct_str': f"{a['total']['pct']:.2f}"}
    return salida


def cargas_con_resumen(proyecto):
    """Las cargas del proyecto, cada una con `resumen` (bultos cargados de cuántos, faltantes) salvo las anuladas."""
    from .acciones import carga_a_dic
    cargas = list(Carga.objects.filter(proyecto=proyecto).select_related('creada_por', 'anulada_por', 'proyecto'))
    for c in cargas:
        c.resumen = carga_a_dic(c) if c.estado != Carga.Estado.ANULADA else None
    return cargas


def muebles_para_cargar(proyecto, piezas=None):
    """Para elegir los muebles de una carga (alta y Modificar): cada mueble con su paso, si todavía falta enviarlo y
    qué procesos completó (para el filtro). (elegibles, procesos prendidos)."""
    from .acciones import pendientes_de_envio
    from .models import procesos
    from .pasos import avance_de_proceso, pasos, pasos_activos
    piezas = piezas_de(proyecto) if piezas is None else piezas
    if not piezas:
        return [], []
    prendidos = [e for e in procesos() if e.activa]
    hechos = {}
    for e in prendidos:
        for n, m in avance_de_proceso(proyecto, e, piezas)['muebles'].items():
            if m['estado'] in ('hecho', 'obs'):
                hechos.setdefault(n, []).append(e.pk)
    nombres = {k: n for k, n, _ in pasos_activos()}
    pendientes = set(pendientes_de_envio(proyecto))
    elegibles = [{'nombre': n, 'paso': nombres.get(m['paso'], ''), 'pendiente': n in pendientes,
                  'hechos': hechos.get(n, [])} for n, m in pasos(proyecto, piezas)['muebles'].items()]
    return elegibles, prendidos
