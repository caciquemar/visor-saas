"""En qué paso está cada mueble, del armado a la instalación (ficha 18): armado → control → embalado → cargado →
entregado → instalado. Lo usan la Lista de entrega, el 3D ("Colorear por entrega"), la pantalla del proyecto, el
tablero y el estado del pedido, así las cuentas son las mismas en todos lados.

El paso es el más avanzado que tiene: un mueble con algún bulto en el camión está "cargado" aunque le falten bultos
(los números x/y lo dicen).

Ficha 19: los pasos salen de los procesos fijos prendidos, con el nombre que les puso el taller. "Entregado" solo existe
si Instalar en obra está apagado (con instalación, los bultos se entregan al instalar y el mueble sigue "cargado" hasta
entonces)."""
from trabajos.api import hora, nombre

from .calculo import avance, piezas_de
from .models import Anotacion, Bulto, Control, Etapa, Instalacion, etapa_de_armado, procesos

# (clave, nombre, color, proceso fijo del que sale): el mismo color en la Lista, el 3D y el tablero
TODOS = [
    ('sin_armar', 'Sin armar', '#CFD8DC', None),
    ('armado', 'Armado', '#F2C94C', Etapa.Tipo.ARMADO),
    ('controlado', 'Control', '#56CCF2', Etapa.Tipo.CONTROL),
    ('embalado', 'Embalado', '#F2994A', Etapa.Tipo.EMBALAJE),
    ('cargado', 'Cargado', '#2F80ED', Etapa.Tipo.CARGA),
    ('entregado', 'Entregado', '#9B51E0', None),
    ('instalado', 'Instalado', '#27AE60', Etapa.Tipo.INSTALACION),
]


def pasos_activos():
    """[(clave, nombre, color)] de los pasos según los procesos prendidos, con el nombre del proceso (Armado se llama
    como el taller lo llamó). "Entregado" solo sin instalación y con carga."""
    prendidos = {e.tipo: e for e in procesos() if e.fijo and e.activa}
    salida = []
    for clave, nombre_, color, tipo in TODOS:
        if clave == 'entregado':
            if Etapa.Tipo.INSTALACION in prendidos or Etapa.Tipo.CARGA not in prendidos:
                continue
        elif tipo is not None:
            if tipo not in prendidos:
                continue
            if clave == 'armado':
                nombre_ = prendidos[tipo].nombre
        salida.append((clave, nombre_, color))
    return salida


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


def anotacion_a_dic(a):
    return {'id': a.pk, 'mueble': a.mueble, 'panel': a.panel, 'pieza': a.pieza,
            'proceso': a.proceso.nombre if a.proceso_id else '', 'texto': a.texto, 'tarea': a.tarea_id,
            **quien_cuando(a.por, a.cuando), 'fotos': [f.pk for f in a.fotos.all()]}


def pasos(proyecto, piezas=None, a=None):
    """{'muebles': {nombre: {...}}, 'totales': {paso: cuántos}, 'controles': {ok, obs, sin}}. Cada mueble: piezas,
    armadas, armado (todas en la etapa de armado), control, fin, bultos (total, cargados, entregados), instalacion y
    paso. `controles` cuenta el último control de cada mueble aparte del paso: un mueble ya embalado o cargado que se
    controla después sigue en su paso, pero su control tiene que verse igual."""
    piezas = piezas_de(proyecto) if piezas is None else piezas
    a = avance(proyecto, piezas) if a is None else a
    activos = pasos_activos()
    hay = {p[0] for p in activos}
    armado = etapa_de_armado()
    controles = {}
    for c in Control.objects.filter(proyecto=proyecto).select_related('por').order_by('cuando', 'pk'):
        controles[c.mueble] = c                                       # vale el último
    bultos = {}
    for b in Bulto.objects.filter(proyecto=proyecto, fin__anulado_en__isnull=True):
        bultos.setdefault(b.mueble, []).append(b)
    instalaciones = {i.mueble: i for i in Instalacion.objects.filter(proyecto=proyecto, anulado_en__isnull=True)
                     .select_related('por').prefetch_related('fotos')}
    anotaciones = {}
    for x in (Anotacion.objects.filter(proyecto=proyecto).select_related('por', 'proceso')
              .prefetch_related('fotos').order_by('-cuando', '-pk')):
        anotaciones.setdefault(x.mueble, []).append(anotacion_a_dic(x))
    muebles, totales, controles_ = {}, {p[0]: 0 for p in activos}, {'ok': 0, 'obs': 0, 'sin': 0}
    for n, m in sorted(a['muebles'].items(), key=lambda kv: kv[0].lower()):
        armadas = m['por_etapa'][armado.pk] if armado else 0
        bs = bultos.get(n, [])
        cargados = sum(1 for b in bs if b.estado in (Bulto.Estado.CARGADO, Bulto.Estado.ENTREGADO))
        entregados = sum(1 for b in bs if b.estado == Bulto.Estado.ENTREGADO)
        inst, c, fin = instalaciones.get(n), controles.get(n), m['fin']
        # el más avanzado de los pasos prendidos (sin correlatividad: puede estar instalado sin control, por ejemplo)
        if inst and 'instalado' in hay:
            paso = 'instalado'
        elif bs and entregados == len(bs) and 'entregado' in hay:
            paso = 'entregado'
        elif cargados and 'cargado' in hay:
            paso = 'cargado'
        elif fin and 'embalado' in hay:
            paso = 'embalado'
        elif c and 'controlado' in hay:
            paso = 'controlado'
        elif m['piezas'] and armadas == m['piezas'] and 'armado' in hay:
            paso = 'armado'
        else:
            paso = 'sin_armar'
        totales[paso] += 1
        controles_['sin' if c is None else 'ok' if c.ok else 'obs'] += 1
        muebles[n] = {
            'piezas': m['piezas'], 'armadas': armadas, 'armado': bool(m['piezas']) and armadas == m['piezas'],
            'control': control_a_dic(c), 'fin': quien_cuando(fin.por, fin.cuando) if fin else None,
            'bultos': {'total': len(bs), 'cargados': cargados, 'entregados': entregados},
            'instalacion': instalacion_a_dic(inst), 'paso': paso, 'anotaciones': anotaciones.get(n, []),
        }
    return {'muebles': muebles, 'totales': totales, 'controles': controles_, 'pasos': activos,
            'con_control': 'controlado' in hay}


# ---------------------------------------------------------------- avance de un proceso (ficha 20)

COLORES_AVANCE = {'hecho': '#27AE60', 'parcial': '#F2994A', 'obs': '#EB5757', 'falta': '#CFD8DC'}
NOMBRES_AVANCE = {'hecho': 'Hecho', 'parcial': 'A medias', 'obs': 'Con observaciones', 'falta': 'Falta'}


def avance_de_proceso(proyecto, etapa, piezas=None):
    """Para la Lista y el 3D de Mi puesto: qué muebles (y, en un proceso por pieza, qué piezas) cumplieron ese
    proceso. {'muebles': {nombre: {estado, por, cuando, hechas, de}}, 'paneles': {id del panel: bool} (solo en los
    procesos que marcan piezas), 'totales': {estado: cuántos muebles}, 'por_pieza': bool}. Estado: 'hecho',
    'parcial' (algunas piezas o algunos bultos), 'obs' (control con observaciones) o 'falta'."""
    from .calculo import marcas_vigentes
    piezas = piezas_de(proyecto) if piezas is None else piezas
    por_mueble_ = {}
    for x in piezas:
        por_mueble_.setdefault(x['panel']['mueble'], []).append(x)
    muebles, paneles = {}, {}

    def poner(n, estado, por=None, cuando=None, hechas=None, de=None):
        muebles[n] = {'estado': estado, **quien_cuando(por, cuando), 'hechas': hechas, 'de': de}

    if etapa.marca_piezas:
        ultima = {}
        for m in marcas_vigentes(proyecto, [etapa]).select_related('por').order_by('cuando', 'pk'):
            ultima[m.huella] = m
        for n, xs in por_mueble_.items():
            hechas = [ultima[x['huella']] for x in xs if x['huella'] in ultima]
            for x in xs:
                paneles[x['panel']['id']] = x['huella'] in ultima
            u = max(hechas, key=lambda m: m.cuando) if hechas else None
            estado = 'hecho' if len(hechas) == len(xs) else 'parcial' if hechas else 'falta'
            poner(n, estado, u.por if u else None, u.cuando if u else None, len(hechas), len(xs))
    elif etapa.tipo == Etapa.Tipo.CONTROL:
        ultimo = {c.mueble: c for c in Control.objects.filter(proyecto=proyecto).select_related('por')
                  .order_by('cuando', 'pk')}
        for n in por_mueble_:
            c = ultimo.get(n)
            poner(n, 'falta' if c is None else 'hecho' if c.ok else 'obs', c and c.por, c and c.cuando)
    elif etapa.tipo == Etapa.Tipo.EMBALAJE:
        from .models import FinDeMueble
        fines = {f.mueble: f for f in FinDeMueble.objects.filter(proyecto=proyecto, anulado_en__isnull=True)
                 .select_related('por')}
        for n in por_mueble_:
            f = fines.get(n)
            poner(n, 'hecho' if f else 'falta', f and f.por, f and f.cuando, f.bultos if f else None)
    elif etapa.tipo == Etapa.Tipo.CARGA:
        bultos = {}
        for b in Bulto.objects.filter(proyecto=proyecto, fin__anulado_en__isnull=True).select_related('cargado_por'):
            bultos.setdefault(b.mueble, []).append(b)
        for n in por_mueble_:
            bs = bultos.get(n, [])
            cargados = [b for b in bs if b.estado != Bulto.Estado.EMBALADO]
            u = max(cargados, key=lambda b: b.cargado_en or b.embalado_en) if cargados else None
            estado = 'hecho' if bs and len(cargados) == len(bs) else 'parcial' if cargados else 'falta'
            poner(n, estado, u and u.cargado_por, u and u.cargado_en, len(cargados), len(bs))
    else:                                                  # instalación
        inst = {i.mueble: i for i in Instalacion.objects.filter(proyecto=proyecto, anulado_en__isnull=True)
                .select_related('por')}
        for n in por_mueble_:
            i = inst.get(n)
            poner(n, 'hecho' if i else 'falta', i and i.por, i and i.cuando)
    totales = {k: 0 for k in COLORES_AVANCE}
    for m in muebles.values():
        totales[m['estado']] += 1
    return {'muebles': dict(sorted(muebles.items(), key=lambda kv: kv[0].lower())), 'paneles': paneles,
            'totales': totales, 'por_pieza': etapa.tipo == Etapa.Tipo.PIEZA and not etapa.por_mueble}
