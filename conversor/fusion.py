"""Proyectos de Autodesk Fusion (ficha 24): el DXF que exporta Fusion, sin lista de OptiCut.

El DXF de Fusion trae un bloque por componente, anidados como en el árbol del diseño (Fusion agrega "(1)", "(2)"…
a las copias), y cada cuerpo como 3DSOLID (ACIS binario), en centímetros con la escala en los INSERT y con Y
arriba. No trae materiales (todo en la capa 0), ni números de mecanizado, cantos o taladros.

Cada cuerpo es una pieza. Los materiales los elige el taller en el visor y llegan en `opciones`:

    {"arriba": "y" | "z",                    eje vertical en Fusion (Y por defecto)
     "todo": "Pino",                         tablero de la biblioteca para todo el proyecto
     "piezas": {"pata": "Eucalipto",         por nombre de pieza (sin el "(n)" de Fusion): otro tablero,
                "almohadones": "-"}}         o "-" = no se fabrica (va como herraje: se ve, no se cuenta)
"""
import logging
import re
from pathlib import Path

import ezdxf
from ezdxf.math import Matrix44

from .polyboard_a_app import ErrorConversion, armar, bbox, materiales, medidas

log = logging.getLogger('conversor')

NO_SE_FABRICA = '-'


def _arreglar_ezdxf():
    """ezdxf 1.4 lee el `transform` de un cuerpo SAB solo como texto (como en SAT); Fusion lo guarda también como
    cuatro vectores (las tres filas de la rotación y la traslación). Sin esto, ese cuerpo no se puede leer."""
    from ezdxf.acis import sab
    from ezdxf.acis.const import Tags
    lector = sab.SabDataLoader
    if getattr(lector, '_visor_transform', False):
        return
    original = lector.read_transform

    def read_transform(self):
        if self.data[self.index].tag in (Tags.LOCATION_VEC, Tags.DIRECTION_VEC):
            valores = []
            for _ in range(4):
                valores += self.read_vec3()
            return valores
        return original(self)
    lector.read_transform = read_transform
    lector._visor_transform = True


def es_de_fusion(dxf):
    """¿DXF con sólidos y sin caras (Fusion)? Polyboard exporta 3DFACE y nunca 3DSOLID. Se recorre como texto, de a
    pedazos y sin armar el documento. `dxf`: ruta o archivo abierto en binario (queda al principio)."""
    if hasattr(dxf, 'read'):
        dxf.seek(0)
        try:
            return _sin_caras_con_solidos(dxf)
        finally:
            dxf.seek(0)
    try:
        with open(dxf, 'rb') as f:
            return _sin_caras_con_solidos(f)
    except OSError:
        return False


def _sin_caras_con_solidos(f):
    solidos, cola = False, b''
    while pedazo := f.read(1024 * 1024):
        texto = cola + pedazo
        if b'\n3DFACE' in texto:
            return False
        solidos = solidos or b'\n3DSOLID' in texto
        cola = texto[-16:]
    return solidos


def base(nombre):
    """'pata(3)' -> 'pata': el nombre de la pieza sin el número de copia de Fusion."""
    return re.sub(r'\s*\(\d+\)\s*$', '', nombre).strip() or nombre


def _caras(entidad, m, girar):
    """Caras del sólido en mm, con Z arriba, como en el DXF de Polyboard: cuadriláteros [a, b, c, d] (un
    triángulo repite el último vértice). Los polígonos de más lados se abren en abanico."""
    from ezdxf.acis import api as acis
    caras = []
    for cuerpo in acis.load_dxf(entidad):
        for malla in acis.mesh_from_body(cuerpo):
            malla.transform(m)
            v = [girar.transform(p) for p in malla.vertices]
            for cara in malla.faces:
                pts = [tuple(v[i]) for i in cara]
                if len(pts) == 4:
                    caras.append(pts)
                else:
                    for k in range(1, len(pts) - 1):
                        caras.append([pts[0], pts[k], pts[k + 1], pts[k + 1]])
    return caras


def leer_fusion(dxf, arriba='y'):
    """[(ruta de bloques, caras)] de cada sólido, y los nombres de los bloques de primer nivel con sus hijos."""
    _arreglar_ezdxf()
    nombre_archivo = Path(dxf).name
    try:
        doc = ezdxf.readfile(dxf)
    except (IOError, ezdxf.DXFError, UnicodeDecodeError, ValueError) as e:
        log.warning(f"{nombre_archivo}: ezdxf no lo pudo leer: {e}")
        raise ErrorConversion(f"No se pudo abrir {nombre_archivo}: el archivo está dañado o no es un DXF. "
                              "Exportalo de nuevo desde Fusion (Archivo → Exportar → DXF).") from e
    # Fusion: X derecha, Y arriba, Z hacia adelante -> como Polyboard: X derecha, Y atrás, Z arriba
    girar = Matrix44([1, 0, 0, 0, 0, 0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1]) if arriba != 'z' else Matrix44()
    solidos, fallidos = [], []

    def recorrer(bloque, m, ruta):
        for e in bloque:
            if e.dxftype() == 'INSERT':
                recorrer(doc.blocks[e.dxf.name], e.matrix44() * m, ruta + [e.dxf.name])
            elif e.dxftype() == '3DSOLID':
                try:
                    caras = _caras(e, m, girar)
                except Exception as error:             # ACIS que ezdxf no entiende: se avisa y se sigue
                    log.warning(f"{nombre_archivo}: no se pudo leer un sólido de {'/'.join(ruta)}: {error}")
                    caras = []
                if caras:
                    solidos.append((ruta, caras))
                else:
                    fallidos.append(ruta[-1])

    primer_nivel = []
    for e in doc.modelspace():
        if e.dxftype() == 'INSERT':
            hijos = any(x.dxftype() == 'INSERT' for x in doc.blocks[e.dxf.name])
            primer_nivel.append((e.dxf.name, hijos))
            recorrer(doc.blocks[e.dxf.name], e.matrix44(), [e.dxf.name])
    for e in doc.modelspace():                      # cuerpos sueltos, fuera de todo componente
        if e.dxftype() == '3DSOLID':
            recorrer([e], Matrix44(), [Path(dxf).stem])
    if not solidos:
        raise ErrorConversion(f"{nombre_archivo} no tiene piezas en 3D. Exportá el diseño desde Fusion como DXF "
                              "con los cuerpos (no un boceto ni un plano).")
    return solidos, primer_nivel, fallidos


def convertir_fusion(dxf, destino, texturas=None, *, biblioteca=None, codigo=None, sin_canto=None, opciones=None):
    opciones = opciones or {}
    elegidos = {base(k).lower(): v for k, v in (opciones.get('piezas') or {}).items()}
    todo = opciones.get('todo') or ''
    proyecto = Path(dxf).stem
    solidos, primer_nivel, fallidos = leer_fusion(dxf, opciones.get('arriba', 'y'))

    # un mueble por archivo; o uno por componente de primer nivel si todos son conjuntos
    por_componente = len(primer_nivel) > 1 and all(hijos for _, hijos in primer_nivel)
    paneles, herrajes, grupos = [], [], {}
    for ruta, caras in solidos:
        mueble = base(ruta[0]) if por_componente else proyecto
        nombre = base(ruta[-1])
        eleccion = elegidos.get(nombre.lower())
        grupos.setdefault(nombre, 0)
        grupos[nombre] += 1
        # ruta para el id de la pieza (armar() saltea el primer bloque): el mueble y el camino dentro del diseño
        ruta_id = [mueble] + (ruta[1:] if por_componente else ruta)
        if eleccion == NO_SE_FABRICA:
            herrajes.append(dict(mueble=mueble, caras=caras))
            continue
        mat = eleccion or todo
        p = dict(ruta=ruta_id, inst=0, caras=caras, capas=[mat] * len(caras), mueble=mueble, nombre=nombre,
                 num='', pieza='', asignado=False, cant=1, taladros=[], bb=bbox(caras))
        p['med'] = medidas(caras)
        p['mat'], p['cantos'] = materiales(p)
        for c in p['cantos']:            # madera maciza: los lados son del mismo material que la pieza
            c['mat'] = mat
        paneles.append(p)

    avisos = [f"No se pudo leer la pieza {n} del DXF: no va a aparecer en el 3D." for n in fallidos]
    sin_material = sorted({p['nombre'] for p in paneles if not p['mat']})
    if sin_material:
        avisos.append("Piezas sin material (elegilo en Materiales de Fusion): " + ', '.join(sin_material) + '.')
    extra = dict(fusion=dict(grupos=[dict(nombre=n, cant=c, eleccion=elegidos.get(n.lower(), ''))
                                     for n, c in sorted(grupos.items(), key=lambda x: x[0].lower())],
                             arriba=opciones.get('arriba', 'y'), todo=todo))
    return armar(proyecto, paneles, herrajes, [], avisos, destino, texturas or [], [], biblioteca=biblioteca,
                 codigo=codigo, sin_canto=sin_canto, extra=extra)
