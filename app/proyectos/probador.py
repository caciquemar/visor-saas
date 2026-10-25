"""Probador de colores del link del cliente (ficha 14).

El taller arma grupos de tableros del proyecto que cambian juntos ("Frentes", "Cuerpos") y elige qué tableros de su
biblioteca ofrecer. El cliente prueba en el visor (visor/index.html hace la misma sustitución que `sustituir`) y,
para la realidad aumentada, pide la combinación: sus GLB se arman en la cola desde `clientes/<código>.json` con el
`glb_ar` del conversor, sin el DXF ni el .ocp. Se guardan hasta LIMITE_COMBINACIONES por versión; pasado eso, el
visor arma el modelo en el celular.

Reglas de sustitución (ver docs/decisiones.md):
- las piezas de un tablero del grupo pasan al tablero elegido;
- los cantos que se llaman como un tablero cambiado (sin mayúsculas ni acentos) pasan al mismo nombre nuevo, así
  siguen viéndose como el tablero; los demás cantos quedan.
"""
import copy
import hashlib
import json
import logging
from pathlib import Path, PurePosixPath

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from conversor.polyboard_a_app import clave, glb_ar

from .models import GrupoDeColor, Material

log = logging.getLogger('visor.probador')

LIMITE_COMBINACIONES = 20       # por versión (decisión de Martín, 2026-10-11)
CARPETA_OPCIONES = 'opciones'   # data/opciones/<id><ext> en el link del cliente
CARPETA_COMBINACIONES = 'combinaciones'


def ruta_cliente(version):
    return f'{version.carpeta()}resultado/clientes/{version.proyecto.codigo_cliente}.json'


def leer_cliente(version):
    """clientes/<código>.json de la versión, o None si no está (datos viejos o versión sin convertir)."""
    try:
        with default_storage.open(ruta_cliente(version), 'rb') as f:
            return json.loads(f.read().decode('utf-8'))
    except (OSError, ValueError):
        return None


def tableros_de(cliente):
    """Tableros que usa el proyecto, en orden alfabético (sin repetir)."""
    return sorted({p['mat'] for p in (cliente or {}).get('paneles', []) if p.get('mat')}, key=clave)


def textura_de(material):
    """Ruta relativa de la textura de una opción, como la pide el visor (data/opciones/<id><ext>)."""
    if not material.textura:
        return None
    return f'{CARPETA_OPCIONES}/{material.pk}{Path(material.textura.name).suffix.lower()}'


def info_de(material):
    """Entrada de `materiales` para un tablero de la biblioteca."""
    info = {}
    if material.textura:
        info['textura'] = textura_de(material)
        # la imagen va como se subió (el conversor no la procesa): con su alto, y girada si la veta es vertical
        ancho = material.ancho_mm or (1000 if material.proporcion else None)
        if ancho:
            info['ancho'] = ancho
        if material.proporcion:
            info['alto'] = round(ancho * material.proporcion)
        if material.veta_efectiva == 'v':
            info['girar'] = 1
    if material.color:
        info['color'] = material.color
    return info


def grupos_vigentes(proyecto, cliente):
    """Los grupos que se le muestran al cliente con esta versión: con al menos un tablero del proyecto y una opción.
    [{grupo, tableros: [nombres], opciones: [Material]}]"""
    presentes = {clave(t): t for t in tableros_de(cliente)}
    grupos = list(GrupoDeColor.objects.filter(proyecto=proyecto))
    ids = {pk for g in grupos for pk in g.opciones}
    materiales = {m.pk: m for m in Material.objects.filter(pk__in=ids, tipo=Material.Tipo.TABLERO)}
    vigentes = []
    for g in grupos:
        tableros = [presentes[clave(t)] for t in g.tableros if clave(t) in presentes]
        opciones = sorted((materiales[pk] for pk in g.opciones if pk in materiales), key=lambda m: m.clave)
        if tableros and opciones:
            vigentes.append({'grupo': g, 'tableros': tableros, 'opciones': opciones})
    return vigentes


def para_el_visor(vigentes):
    """window.VISOR.probador: lo que necesita el selector de colores del link del cliente."""
    return [{'id': v['grupo'].pk, 'nombre': v['grupo'].nombre, 'tableros': v['tableros'],
             'opciones': [{'id': m.pk, 'nombre': m.nombre, **info_de(m)} for m in v['opciones']]}
            for v in vigentes]


def normalizar(elecciones, vigentes):
    """{id de grupo: id de Material} solo con grupos y opciones válidos. Una opción que es el mismo tablero que
    el grupo ya tiene (grupo de un solo tablero) no es un cambio."""
    if not isinstance(elecciones, dict):
        return {}
    por_id = {v['grupo'].pk: v for v in vigentes}
    limpias = {}
    for g, m in elecciones.items():
        try:
            g, m = int(g), int(m)
        except (TypeError, ValueError):
            continue
        v = por_id.get(g)
        material = v and next((x for x in v['opciones'] if x.pk == m), None)
        if material is None:
            continue
        if all(clave(t) == material.clave for t in v['tableros']):
            continue
        limpias[g] = m
    return dict(sorted(limpias.items()))


def cambios_de(elecciones, vigentes):
    """{nombre del tablero del proyecto: Material elegido}."""
    por_id = {v['grupo'].pk: v for v in vigentes}
    cambios = {}
    for g, m in elecciones.items():
        v = por_id[g]
        material = next(x for x in v['opciones'] if x.pk == m)
        for t in v['tableros']:
            cambios[t] = material
    return cambios


def sustituir(cliente, cambios):
    """Copia de cliente.json con los tableros cambiados (ver las reglas arriba). `cambios`: {tablero: Material}.
    La misma regla está en visor/index.html (probadorSustituir)."""
    d = copy.deepcopy(cliente)
    if not cambios:
        return d
    nuevo = {t: m.nombre for t, m in cambios.items()}
    por_clave = {clave(t): m.nombre for t, m in cambios.items()}
    for p in d.get('paneles', []):
        if p.get('mat') in nuevo:
            p['mat'] = nuevo[p['mat']]
        for c in p.get('cantos') or []:
            if c.get('mat') and clave(c['mat']) in por_clave:
                c['mat'] = por_clave[clave(c['mat'])]
    materiales = d.setdefault('materiales', {})
    for m in cambios.values():
        materiales[m.nombre] = info_de(m)
        # un canto que acompaña puede quedar en una pieza de otro tablero: que tenga el color del elegido
        if 'cantos' in d and m.color:
            d['cantos'][m.nombre] = {'color': m.color}
    return d


def elegidos(elecciones, vigentes):
    """Foto de los nombres para guardar una elección: [{grupo, tableros, elegido}]."""
    foto = []
    for v in vigentes:
        m = elecciones.get(v['grupo'].pk)
        material = next((x for x in v['opciones'] if x.pk == m), None)
        foto.append({'grupo': v['grupo'].nombre, 'tableros': v['tableros'],
                     'elegido': material.nombre if material else None})      # None: como está
    return foto


def clave_de(elecciones, vigentes):
    """Clave corta de una combinación: las elecciones y la fecha de cada material elegido (si el taller cambia la
    textura o el color de uno, la combinación se vuelve a generar)."""
    materiales = {m.pk: m for v in vigentes for m in v['opciones']}
    texto = json.dumps([[g, m, materiales[m].actualizado.isoformat()] for g, m in sorted(elecciones.items())])
    return hashlib.sha1(texto.encode()).hexdigest()[:16]


def carpeta_de(combinacion):
    return f'{combinacion.version.carpeta()}resultado/{CARPETA_COMBINACIONES}/{combinacion.clave}/'


def bajar(nombre, destino):
    destino.parent.mkdir(parents=True, exist_ok=True)
    with default_storage.open(nombre, 'rb') as origen:
        destino.write_bytes(origen.read())


def generar(combinacion, tmp):
    """Arma y sube los GLB de la combinación (todo el proyecto y cada mueble, como `version_cliente`). Devuelve
    el dict `ar` ({mueble o '': ruta relativa a data/}). Lanza si no se puede."""
    version = combinacion.version
    cliente = leer_cliente(version)
    if cliente is None:
        raise ValueError('la versión no tiene clientes/<código>.json')
    vigentes = grupos_vigentes(version.proyecto, cliente)
    elecciones = normalizar(combinacion.elecciones, vigentes)
    d = sustituir(cliente, cambios_de(elecciones, vigentes))
    # texturas que se usan, en la carpeta temporal con la misma ruta relativa que en el resultado
    materiales = d.get('materiales', {})
    usados = {p['mat'] for p in d['paneles']}
    opciones = {textura_de(m): m for v in vigentes for m in v['opciones'] if m.textura}
    base = f'{version.carpeta()}resultado/'
    for nombre in usados:
        tex = (materiales.get(nombre) or {}).get('textura')
        if not tex or (tmp / tex).exists():
            continue
        try:
            bajar(opciones[tex].textura.name if tex in opciones else base + tex, tmp / tex)
        except (OSError, KeyError):
            log.warning('Combinación %s: falta la textura %s', combinacion.pk, tex)   # queda el color
    carpeta = carpeta_de(combinacion)
    ar = {}
    for i, mueble in enumerate([None] + d['muebles']):
        pan = [p for p in d['paneles'] if mueble is None or p['mueble'] == mueble]
        her = [h for h in d['herrajes'] if mueble is None or h['mueble'] == mueble]
        glb = glb_ar(d, pan, her, tmp, {}, sin_canto=version.taller.color_sin_canto)
        if glb:
            nombre = 'todo.glb' if mueble is None else f'mueble-{i}.glb'
            if default_storage.exists(carpeta + nombre):      # un intento anterior: save() no pisa, renombra
                default_storage.delete(carpeta + nombre)
            default_storage.save(carpeta + nombre, ContentFile(glb))
            ar[mueble or ''] = str(PurePosixPath(CARPETA_COMBINACIONES, combinacion.clave, nombre))
    return ar
