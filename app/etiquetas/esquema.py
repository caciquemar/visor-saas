"""El esquema de la etiqueta del mueble (ficha 19): el mueble, o el proyecto entero con el mueble marcado, visto de
frente. El frente es el **del mueble**, no el del proyecto: en una cocina en L, el mueble del costado se dibuja
mirándolo de frente y el resto del proyecto se ve desde ese mismo lado.

Sin Django: recibe el proyecto.json ya leído. Cada pieza se dibuja como la caja de su proyección en esa vista (como
los planos del visor), de atrás hacia adelante.

Hacia dónde mira un mueble no viene en el proyecto, y los cantos "frente"/"atrás" son de cada pieza, no del mueble.
Sale de los nombres que pone Polyboard: el Lateral Derecho queda a la derecha de quien mira, la Trasera atrás y las
puertas y frentes adelante (se suman las tres señales). Sin ninguna, el frente del proyecto."""
import math
import re

# sin nada que lo diga, el frente es el del proyecto: +z (los muros quedan atrás, en z negativo)
FRENTE_DEL_PROYECTO = (0.0, 1.0)
# en el proyecto: lo que está hasta 1,5 m a cada lado del mueble, sin lo que queda entre quien mira y el mueble
ALREDEDOR = 1500
DELANTE = 50
DERECHO = re.compile(r'^lat\w*\.?\s*der', re.I)
IZQUIERDO = re.compile(r'^lat\w*\.?\s*izq', re.I)
TRASERA = re.compile(r'^(trasera|fondo\b|espalda)', re.I)
FRENTES = re.compile(r'^(puerta|frente|caj[oó]n|tapa caj)', re.I)


def _centro(t):
    """Centro de la caja de los vértices (x, y, z) de una pieza."""
    return [(min(t[i::3]) + max(t[i::3])) / 2 for i in range(3)]


def _unitario(x, z):
    largo = math.hypot(x, z)
    return (x / largo, z / largo) if largo > 1e-6 else (0.0, 0.0)


def frente_del_mueble(proyecto, mueble):
    """(fx, fz): hacia dónde mira el frente del mueble en el plano horizontal, siempre a lo largo de un eje (los
    muebles van a escuadra; en un esquinero en L las señales dan en diagonal y se toma el eje más cercano)."""
    piezas = [p for p in proyecto.get('paneles', []) if p.get('mueble') == mueble and len(p.get('t') or []) >= 9]
    if not piezas:
        return FRENTE_DEL_PROYECTO
    todo = [v for p in piezas for v in p['t']]
    cx, _, cz = _centro(todo)
    sx = sz = 0.0
    # 1. la derecha de quien mira: del Lateral Izquierdo al Derecho; el frente queda girado 90° (f = (-r.z, r.x))
    der = [_centro(p['t']) for p in piezas if DERECHO.search(p.get('nombre', ''))]
    izq = [_centro(p['t']) for p in piezas if IZQUIERDO.search(p.get('nombre', ''))]
    if der and izq:
        rx = sum(c[0] for c in der) / len(der) - sum(c[0] for c in izq) / len(izq)
        rz = sum(c[2] for c in der) / len(der) - sum(c[2] for c in izq) / len(izq)
        ux, uz = _unitario(rx, rz)
        sx, sz = sx - uz, sz + ux
    # 2. la trasera queda atrás y 3. las puertas y frentes adelante, respecto del centro del mueble
    for patron, signo in ((TRASERA, -1), (FRENTES, 1)):
        cs = [_centro(p['t']) for p in piezas if patron.search(p.get('nombre', ''))]
        if cs:
            ux, uz = _unitario(sum(c[0] for c in cs) / len(cs) - cx, sum(c[2] for c in cs) / len(cs) - cz)
            sx, sz = sx + signo * ux, sz + signo * uz
    if math.hypot(sx, sz) < 1e-6:
        return FRENTE_DEL_PROYECTO
    if abs(sx) > abs(sz):
        return (math.copysign(1.0, sx), 0.0)
    return (0.0, math.copysign(1.0, sz))


def esquema(proyecto, mueble, todo=False):
    """Las piezas proyectadas en la vista de frente del mueble: [{'caja': (u0, v0, u1, v1), 'del_mueble': bool}],
    de atrás hacia adelante, en mm (u a la derecha de quien mira, v hacia arriba). Con `todo`, también las de los
    otros muebles alrededor (hasta 1,5 m a cada lado, sin las que quedan delante del mueble y lo taparían); si no,
    solo las del mueble. Vacío si el mueble no tiene piezas con geometría."""
    fx, fz = frente_del_mueble(proyecto, mueble)
    rx, rz = fz, -fx                                      # a la derecha de quien mira hacia el mueble
    salida = []
    for p in proyecto.get('paneles', []):
        propio = p.get('mueble') == mueble
        if not (propio or todo):
            continue
        t = p.get('t') or []
        if len(t) < 9:
            continue
        us, vs, ds = [], [], []
        for i in range(0, len(t) - 2, 3):
            x, y, z = t[i], t[i + 1], t[i + 2]
            us.append(x * rx + z * rz)
            vs.append(y)
            ds.append(x * fx + z * fz)
        salida.append({'caja': (min(us), min(vs), max(us), max(vs)), 'del_mueble': propio,
                       'fondo': sum(ds) / len(ds)})
    propias = [x for x in salida if x['del_mueble']]
    if not propias:
        return []
    if todo:
        u0 = min(x['caja'][0] for x in propias) - ALREDEDOR
        u1 = max(x['caja'][2] for x in propias) + ALREDEDOR
        frente = max(x['fondo'] for x in propias) + DELANTE
        salida = [x for x in salida if x['del_mueble'] or (x['caja'][2] > u0 and x['caja'][0] < u1
                                                             and x['fondo'] <= frente)]
    salida.sort(key=lambda x: x['fondo'])                 # lo de atrás primero: lo de adelante lo tapa
    for x in salida:
        del x['fondo']
    return salida
