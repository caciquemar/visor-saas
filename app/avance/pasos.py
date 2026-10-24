"""En qué paso está cada mueble, del armado a la instalación (ficha 18): armado → control → embalado → cargado →
entregado → instalado. Lo usan la Lista de entrega, el 3D ("Colorear por entrega"), la pantalla del proyecto, el
tablero y el estado del pedido, así las cuentas son las mismas en todos lados.

El paso es el más avanzado que tiene: un mueble con algún bulto en el camión está "cargado" aunque le falten bultos
(los números x/y lo dicen)."""
from trabajos.api import hora, nombre

from .calculo import avance, piezas_de
from .models import Bulto, Control, Instalacion, etapas_activas

# (clave, nombre, color): el mismo color en la Lista, el 3D y el tablero
PASOS = [
    ('sin_armar', 'Sin armar', '#CFD8DC'),
    ('armado', 'Armado', '#F2C94C'),
    ('controlado', 'Control', '#56CCF2'),
    ('embalado', 'Embalado', '#F2994A'),
    ('cargado', 'Cargado', '#2F80ED'),
    ('entregado', 'Entregado', '#9B51E0'),
    ('instalado', 'Instalado', '#27AE60'),
]
ORDEN = [p[0] for p in PASOS]


def quien_cuando(por, cuando):
    return {'por': nombre(por), 'cuando': hora(cuando)}


def control_a_dic(c):
    if c is None:
        return None
    return {'ok': c.ok, **quien_cuando(c.por, c.cuando),
            'mal': [r['nombre'] for r in c.resultados if not r.get('ok')], 'resultados': c.resultados}


def instalacion_a_dic(i):
    if i is None:
        return None
    return {'id': i.pk, **quien_cuando(i.por, i.cuando), 'nota': i.nota, 'motivo': i.motivo,
            'faltantes': i.faltantes, 'fotos': [f.pk for f in i.fotos.all()]}


def pasos(proyecto, piezas=None, a=None):
    """{'muebles': {nombre: {...}}, 'totales': {paso: cuántos}, 'controles': {ok, obs, sin}}. Cada mueble: piezas,
    armadas, armado (todas en la etapa de armado), control, fin, bultos (total, cargados, entregados), instalacion y
    paso. `controles` cuenta el último control de cada mueble aparte del paso: un mueble ya embalado o cargado que se
    controla después sigue en su paso, pero su control tiene que verse igual."""
    piezas = piezas_de(proyecto) if piezas is None else piezas
    a = avance(proyecto, piezas) if a is None else a
    activas = etapas_activas()
    armado = activas[-1] if activas else None
    controles = {}
    for c in Control.objects.filter(proyecto=proyecto).select_related('por').order_by('cuando', 'pk'):
        controles[c.mueble] = c                                       # vale el último
    bultos = {}
    for b in Bulto.objects.filter(proyecto=proyecto, fin__anulado_en__isnull=True):
        bultos.setdefault(b.mueble, []).append(b)
    instalaciones = {i.mueble: i for i in Instalacion.objects.filter(proyecto=proyecto, anulado_en__isnull=True)
                     .select_related('por').prefetch_related('fotos')}
    muebles, totales, controles_ = {}, {p: 0 for p in ORDEN}, {'ok': 0, 'obs': 0, 'sin': 0}
    for n, m in sorted(a['muebles'].items(), key=lambda kv: kv[0].lower()):
        armadas = m['por_etapa'][armado.pk] if armado else 0
        bs = bultos.get(n, [])
        cargados = sum(1 for b in bs if b.estado in (Bulto.Estado.CARGADO, Bulto.Estado.ENTREGADO))
        entregados = sum(1 for b in bs if b.estado == Bulto.Estado.ENTREGADO)
        inst, c, fin = instalaciones.get(n), controles.get(n), m['fin']
        if inst:
            paso = 'instalado'
        elif bs and entregados == len(bs):
            paso = 'entregado'
        elif cargados:
            paso = 'cargado'
        elif fin:
            paso = 'embalado'
        elif c:
            paso = 'controlado'
        elif m['piezas'] and armadas == m['piezas']:
            paso = 'armado'
        else:
            paso = 'sin_armar'
        totales[paso] += 1
        controles_['sin' if c is None else 'ok' if c.ok else 'obs'] += 1
        muebles[n] = {
            'piezas': m['piezas'], 'armadas': armadas, 'armado': bool(m['piezas']) and armadas == m['piezas'],
            'control': control_a_dic(c), 'fin': quien_cuando(fin.por, fin.cuando) if fin else None,
            'bultos': {'total': len(bs), 'cargados': cargados, 'entregados': entregados},
            'instalacion': instalacion_a_dic(inst), 'paso': paso,
        }
    return {'muebles': muebles, 'totales': totales, 'controles': controles_}
