"""Qué es una pieza y qué es un mueble para las etiquetas, de modo que la etiqueta impresa siga sirviendo al subir
una versión nueva del proyecto (regla en docs/decisiones.md, 2026-10-10).

Pieza: un panel 3D que está en la lista de OptiCut (`pieza` no vacío). Su clave es (mueble, nombre, número, copia):
`copia` cuenta 1, 2, … los paneles con los mismos tres datos (piezas iguales, `cant` > 1), ordenados por `id` del DXF.
Mueble: su nombre. No se usa el `id` del DXF ni la fila del .ocp porque Polyboard los rearma entre versiones.
"""
from collections import defaultdict


def clave_de_pieza(mueble, nombre, num, copia):
    return {'mueble': mueble, 'nombre': nombre, 'num': num, 'copia': copia}


def piezas(proyecto):
    """Las piezas con etiqueta de un proyecto.json, en el orden en que se imprimen (mueble, número, nombre):
    lista de dicts {clave, panel, copia, de}."""
    grupos = defaultdict(list)
    for p in proyecto.get('paneles', []):
        if p.get('pieza'):
            p = {'id': '', 'num': '', 'nombre': '', 'mueble': '', 'med': [0, 0, 0], **p}
            grupos[(p['mueble'], p['nombre'], p['num'])].append(p)
    salida = []
    for (mueble, nombre, num), paneles in grupos.items():
        paneles.sort(key=lambda p: p['id'])
        for i, p in enumerate(paneles, 1):
            salida.append({'clave': clave_de_pieza(mueble, nombre, num, i), 'panel': p, 'copia': i,
                           'de': len(paneles)})
    salida.sort(key=lambda x: (x['panel']['mueble'].lower(), x['panel']['num'] == '', x['panel']['num'],
                               x['panel']['nombre'].lower(), x['copia']))
    return salida


def muebles(proyecto):
    """Los muebles que tienen piezas con etiqueta: {nombre: cantidad de piezas}."""
    cuenta = defaultdict(int)
    for x in piezas(proyecto):
        cuenta[x['panel']['mueble']] += 1
    return dict(sorted(cuenta.items(), key=lambda kv: kv[0].lower()))


def buscar_pieza(proyecto, clave):
    """El panel de la clave en este proyecto.json, o None si la pieza ya no está."""
    for x in piezas(proyecto):
        if x['clave'] == clave:
            return x
    return None
