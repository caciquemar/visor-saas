#!/usr/bin/env python3
"""
polyboard_a_app.py — Convierte un proyecto de Polyboard (3D DXF + lista OptiCut .ocp)
en un JSON para el visor de armado.

Uso:
    python polyboard_a_app.py proyecto.dxf proyecto.ocp -o data/
    python polyboard_a_app.py proyecto.dxf proyecto.ocp -o data/ --texturas "C:\\...\\PolyBoard-v7.5-en\\Textures"

Genera data/<proyecto>.json y actualiza data/index.json.
Con --texturas, copia reducida de la imagen de cada material en data/texturas/.
Requiere: pip install ezdxf   (y pillow para --texturas)

Desde Python:  from conversor import convertir, ErrorConversion
"""
import argparse, bz2, hashlib, json, logging, math, re, secrets, struct, sys, unicodedata
from dataclasses import dataclass, field
from pathlib import Path
import ezdxf

log = logging.getLogger('conversor')

class ErrorConversion(Exception):
    """El proyecto no se puede convertir. El mensaje es para el taller: dice qué pasó y qué hacer."""

def descomprimir(path):
    """Archivos de Boole (.ocp, .mat-boole): cabecera + bloque bzip2."""
    raw = Path(path).read_bytes()
    i = raw.find(b'BZh9')
    if i < 0:
        return None
    dec = bz2.BZ2Decompressor()
    try:
        d = dec.decompress(raw[i:])
    except (OSError, EOFError):
        return None
    return d if dec.eof else None      # bloque cortado: el archivo está incompleto

# ---------------------------------------------------------------- OCP (OptiCut)
def leer_ocp(path):
    """Devuelve las piezas del .ocp: número, nombre, mueble, proyecto, largo, ancho, cantidad."""
    nombre_archivo = Path(path).name
    if not Path(path).is_file():
        raise ErrorConversion(f"No se encontró el archivo de OptiCut {nombre_archivo}.")
    d = descomprimir(path)
    if d is None:
        raise ErrorConversion(f"{nombre_archivo} no parece una lista de OptiCut (.ocp) o está dañado. "
                              "Volvé a exportarla desde Polyboard.")

    def texto(o):
        if o + 4 > len(d):
            return None, o
        n = struct.unpack_from('<I', d, o)[0]
        if n > 200 or o + 4 + 2 * n > len(d):
            return None, o
        try:
            t = d[o + 4:o + 4 + 2 * n].decode('utf-16-le')
        except UnicodeDecodeError:
            return None, o
        return t, o + 4 + 2 * n

    # Dos versiones de OptiCut:
    #  vieja: [largo, ancho (double)] [cantidad] nombre [ceros] 06 00.. mueble proyecto nº
    #  nueva: [cantidad] [largo, ancho] (45 bytes antes del nombre) ... 07 00.. nombre mueble proyecto nº
    marca_vieja, marca_nueva = b'\x06' + b'\x00' * 7, b'\x07' + b'\x00' * 7
    piezas, o = [], 0
    while o < len(d) - 40:
        nombre, o2 = texto(o)
        if not (nombre and nombre.isprintable()):
            o += 1
            continue
        k = next((k for k in range(0, 7) if d[o2:o2 + k] == b'\x00' * k and d[o2 + k:o2 + k + 8] == marca_vieja), None)
        if k is not None:
            inicio_mueble, medidas, en_cant = o2 + k + 8, o - 24, o - 4
        elif o >= 44 and d[o - 8:o] == marca_nueva:
            inicio_mueble, medidas, en_cant = o2, o - 45, o - 49
        else:
            o += 1
            continue
        mueble, o3 = texto(inicio_mueble)
        proyecto, o4 = texto(o3) if mueble else (None, o3)
        if mueble and proyecto is not None:     # el proyecto puede venir vacío
            numero, o5 = texto(o4)          # nº de mecanizado ('' si no se mecaniza)
            pieza, _ = texto(o5 + 8)        # nº de pieza dentro del mueble
            largo, ancho = struct.unpack_from('<dd', d, medidas)
            cant = struct.unpack_from('<I', d, en_cant)[0]
            if largo > 0 and ancho > 0:
                piezas.append(dict(num=numero or '', pieza=pieza or '', nombre=nombre, mueble=mueble,
                                   proyecto=proyecto, L=round(largo, 1),
                                   W=round(ancho, 1), cant=max(cant, 1)))
                o = o5
                continue
        o += 1
    if not piezas:
        raise ErrorConversion(f"{nombre_archivo} no tiene piezas. Revisá que sea la lista de OptiCut del proyecto.")
    return piezas

# ---------------------------------------------------------------- DXF 3D
def leer_dxf(path):
    """Recorre los bloques del DXF y devuelve paneles, herrajes y muros en coordenadas de mundo."""
    nombre_archivo = Path(path).name
    if not Path(path).is_file():
        raise ErrorConversion(f"No se encontró el archivo 3D {nombre_archivo}.")
    try:
        doc = ezdxf.readfile(path)
    except (IOError, ezdxf.DXFError, UnicodeDecodeError, ValueError) as e:
        raise ErrorConversion(f"No se pudo leer {nombre_archivo} como DXF ({e}). "
                              "Exportá de nuevo el proyecto desde Polyboard como DXF 3D.") from e
    paneles, herrajes, muros, taladros = [], [], [], []

    def caras(block, m):
        tris = []
        capas = caras.capas = []
        for f in block:
            if f.dxftype() != '3DFACE':
                continue
            v = [m.transform(p) for p in (f.dxf.vtx0, f.dxf.vtx1, f.dxf.vtx2, f.dxf.vtx3)]
            tris.append(v)
            capas.append(f.dxf.layer)
        return tris

    def recorrer(block, m, ruta, inst):
        for e in block:
            if e.dxftype() == 'CIRCLE' and e.dxf.get('thickness', 0):
                c = m.transform(e.ocs().to_wcs(e.dxf.center))
                n = m.transform_direction(e.dxf.extrusion).normalize()
                taladros.append(dict(c=c, n=n, d=round(e.dxf.radius * 2, 1),
                                     prof=abs(e.dxf.thickness), ruta=ruta, inst=inst))
        tris = caras(block, m)
        if tris:
            item = dict(ruta=ruta, inst=inst, caras=tris, capas=list(caras.capas))
            if ruta[0].split('.', 1)[-1].lower().startswith('muro'):
                muros.append(item)
            elif len(tris) == 6 or not {'ACCESSORY', '0'} & set(item['capas']):
                # caja de 6 caras, o pieza con ingletes/rebajes (caras en capas de material) = panel
                paneles.append(item)
            else:                     # bisagras, tiradores, correderas
                herrajes.append(item)
        for e in block:
            if e.dxftype() == 'INSERT':
                recorrer(doc.blocks[e.dxf.name], e.matrix44() * m, ruta + [e.dxf.name], inst)

    cuenta = {}
    for e in doc.modelspace():
        if e.dxftype() != 'INSERT':
            continue
        n = e.dxf.name
        cuenta[n] = cuenta.get(n, 0) + 1
        recorrer(doc.blocks[n], e.matrix44(), [n], cuenta[n] - 1)
    if not paneles:
        raise ErrorConversion(f"{nombre_archivo} no tiene muebles. Revisá que sea el DXF 3D del proyecto "
                              "(y no un plano 2D o un mapa de corte).")
    asignar_taladros(paneles, taladros)
    return paneles, herrajes, muros, cuenta

def materiales(p):
    """Material del tablero y cantos enchapados, a partir de la capa de cada cara."""
    import math
    caras, capas = p['caras'], p['capas']
    def area(c):
        a, b, cc = c[0], c[1], c[2]
        u = [b[i] - a[i] for i in range(3)]; v = [cc[i] - a[i] for i in range(3)]
        n = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
        return math.sqrt(sum(x*x for x in n))
    orden = sorted(range(len(caras)), key=lambda i: -area(caras[i]))
    tablero = capas[orden[0]]
    (x0, y0, z0), (x1, y1, z1) = p['bb']
    centro = [(x0+x1)/2, (y0+y1)/2, (z0+z1)/2]
    med = p['med']
    cantos = []
    for i in orden[2:]:
        c = caras[i]
        # largo del canto = mayor distancia entre vértices consecutivos
        lados = [math.dist(c[k], c[(k+1) % 4]) for k in range(4)]
        largo = max(lados)
        fc = [sum(v[k] for v in c)/4 for k in range(3)]
        d = [fc[k] - centro[k] for k in range(3)]
        eje = max(range(3), key=lambda k: abs(d[k]))
        # coordenadas DXF: X derecha, Y fondo (-Y = frente), Z arriba
        pos = {(0, 1): 'derecha', (0, -1): 'izquierda', (1, 1): 'atrás', (1, -1): 'frente',
               (2, 1): 'arriba', (2, -1): 'abajo'}[(eje, 1 if d[eje] > 0 else -1)]
        cantos.append(dict(mat=capas[i] if capas[i] != tablero else '', largo=round(largo, 1),
                           lado='largo' if abs(largo - med[0]) < abs(largo - med[1]) else 'ancho',
                           pos=pos, v=c))
    return tablero, cantos

def asignar_taladros(paneles, taladros):
    """Cada taladro va a la pieza (dentro del mismo bloque) sobre cuya superficie está."""
    for p in paneles:
        p['bb'] = bbox(p['caras']); p['taladros'] = []
    def dist(pt, bb):
        a, b = bb
        return sum(max(a[i] - pt[i], 0, pt[i] - b[i]) ** 2 for i in range(3)) ** .5
    vistos = set()
    for h in taladros:
        cand = [p for p in paneles if p['inst'] == h['inst'] and p['ruta'][:len(h['ruta'])] == h['ruta']]
        if not cand:
            continue
        p = min(cand, key=lambda q: dist(h['c'], q['bb']))
        if dist(h['c'], p['bb']) > 1:
            continue
        clave = (id(p), tuple(round(v) for v in h['c']), tuple(round(v, 2) for v in h['n']), h['d'])
        if clave in vistos:            # Polyboard repite taladros superpuestos
            continue
        vistos.add(clave)
        # profundidad visible: no más allá de la pieza
        a, b = p['bb']; eje = max(range(3), key=lambda i: abs(h['n'][i]))
        largo_eje = b[eje] - a[eje]
        # ¿cara o canto? el espesor es la medida menor de la pieza
        esp = min(range(3), key=lambda i: b[i] - a[i])
        p['taladros'].append(dict(c=h['c'], n=h['n'], d=h['d'], prof=round(h['prof'], 1),
                                  vis=min(h['prof'], largo_eje), canto=eje != esp))

def bbox(caras):
    xs = [p[0] for c in caras for p in c]; ys = [p[1] for c in caras for p in c]; zs = [p[2] for c in caras for p in c]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))

def medidas(caras):
    a, b = bbox(caras)
    return sorted([b[0] - a[0], b[1] - a[1], b[2] - a[2]], reverse=True)

# ---------------------------------------------------------------- vinculación
def base(nombre):
    """'Door Std (doble) [1]_2' -> 'door std (doble)'"""
    n = re.sub(r'\s*\(\d+\)\s*$', '', nombre)
    n = re.sub(r'_\d+$', '', n)
    n = re.sub(r'\s*\[\d+\]', '', n)
    n = re.sub(r'\d+$', '', n)
    return n.strip().lower()

def indice(nombre):
    """Índice explícito al final del nombre: '_4', '(4)'. None si no tiene."""
    m = re.search(r'(?:_|\()(\d+)\)?\s*$', nombre)
    return int(m.group(1)) if m else None

def letra(i):
    return chr(ord('A') + i)

def vincular(piezas, paneles, cuenta):
    proyecto = piezas[0]['proyecto'] if piezas else ''
    # nombre del mueble en el DXF + número de instancia -> nombre del mueble en el OCP
    def mueble_ocp(bloque, inst):
        cab = bloque.split('.', 1)[-1]
        return f"{cab}-{letra(inst)}" if cuenta.get(bloque, 1) > 1 else cab

    for p in paneles:
        p['mueble'] = mueble_ocp(p['ruta'][0], p['inst'])
        pref = p['ruta'][0] + '.'
        p['nombre'] = p['ruta'][1][len(pref):] if len(p['ruta']) > 1 and p['ruta'][1].startswith(pref) else p['mueble']
        hoja = p['ruta'][-1].split('.', 1)[-1]
        p['idx'] = indice(hoja)
        p['med'] = medidas(p['caras'])
        p['num'] = ''
        p['asignado'] = False

    avisos = []
    # primero las piezas con índice explícito (_4), después las agrupadas
    orden = sorted(piezas, key=lambda q: (indice(q['nombre']) is None, q['num'] == '', q['num']))
    for q in orden:
        cand = [p for p in paneles if not p['asignado'] and p['mueble'] == q['mueble']
                and abs(p['med'][0] - max(q['L'], q['W'])) < 1.5
                and abs(p['med'][1] - min(q['L'], q['W'])) < 1.5]
        if not cand:
            avisos.append(f"Sin panel 3D para {q['nombre']} ({q['mueble']}, mec. {q['num'] or '-'})")
            continue
        # preferir mismo nombre base
        mismo = [p for p in cand if base(p['nombre']) == base(q['nombre'])
                 or base(p['ruta'][-1].split('.', 1)[-1]) == base(q['nombre'])]
        cand = mismo or cand
        # ordenar por índice de hoja/grupo para respetar _1.._n
        def orden_panel(p):
            grupo = indice(p['ruta'][1]) if len(p['ruta']) > 1 else None
            return (grupo or 0, p['idx'] or 0)
        cand.sort(key=orden_panel)
        qi = indice(q['nombre'])
        if qi is not None and len(cand) >= 1:
            elegidos = [cand[-1]] if qi > len(cand) else [cand[min(qi, len(cand)) - 1]]
        else:
            elegidos = cand[:q['cant']]
        if len(elegidos) < q['cant']:
            avisos.append(f"{q['nombre']} ({q['mueble']}): se esperaban {q['cant']} y se encontraron {len(elegidos)}")
        for p in elegidos:
            p['asignado'] = True
            p['pieza'] = q['pieza']
            p['num'] = q['num']
            p['nombre_ocp'] = q['nombre']
            p['cant'] = q['cant']
            # Polyboard escribe primero la medida en el sentido de la veta: si el largo del .ocp
            # es el lado menor de la pieza, la veta va a lo ancho (en piezas cuadradas no se sabe)
            p['veta_cruzada'] = abs(q['L'] - q['W']) > 1.5 and q['L'] < q['W']
    return proyecto, avisos

# ---------------------------------------------------------------- texturas
IMAGEN = re.compile(r'\.(jpe?g|jfif|png|bmp|webp|gif|tiff?)$', re.I)
ANCHO_TEXTURA = 1000     # mm que cubre la imagen cuando Polyboard no guarda la escala

def clave(nombre):
    """Nombre de material comparable: sin mayúsculas, acentos ni espacios de más."""
    t = unicodedata.normalize('NFD', str(nombre)).encode('ascii', 'ignore').decode()
    return ' '.join(t.lower().split())

def cadenas(d):
    """Textos UTF-16 con prefijo de largo (formato de Boole): [(inicio, texto, fin)]."""
    out, o = [], 0
    while o < len(d) - 6:
        n = struct.unpack_from('<I', d, o)[0]
        if 2 <= n <= 260 and o + 4 + 2 * n <= len(d):
            try:
                t = d[o + 4:o + 4 + 2 * n].decode('utf-16-le')
            except UnicodeDecodeError:
                t = None
            if t and all(32 <= ord(c) < 0x250 for c in t):
                out.append((o, t, o + 4 + 2 * n))
                o += 4 + 2 * n
                continue
        o += 1
    return out

def texturas_de(path, todos=False):
    """{material: (ruta relativa, ancho en mm o None)} de un .ocp o una biblioteca .mat-boole.
    La ruta de la imagen va justo después del nombre del material; después: 4 bytes de
    opciones, 4 de color y el ancho real de la imagen en mm (infinito = sin escala).
    Con todos=True también figuran, con None, los materiales sin textura (bibliotecas)."""
    d = descomprimir(path)
    if d is None:
        return {}
    ss = cadenas(d)
    res = {t: None for o, t, fin in ss if not IMAGEN.search(t)} if todos else {}
    for k, (o, t, fin) in enumerate(ss):
        if k and IMAGEN.search(t) and not IMAGEN.search(ss[k - 1][1]):
            ancho = struct.unpack_from('<d', d, fin + 8)[0] if fin + 16 <= len(d) else math.inf
            if not res.get(ss[k - 1][1]):
                res[ss[k - 1][1]] = (t, ancho if math.isfinite(ancho) and ancho > 0 else None)
    return res

def registro_tras(d, desde, hasta):
    """Color y espesor de un registro de material. El color: R G B 00, un double entre 0 y 1,
    0xFF y el largo de la ruta de la textura (0 si no tiene); se prueba byte a byte porque la
    cabecera del primer registro trae ceros que parecen un color negro. El espesor (cantos) es
    un double 48 bytes después del fin de la ruta de la textura."""
    for i in range(desde, min(hasta, len(d) - 17)):
        if d[i + 3] or d[i + 12] != 0xFF:
            continue
        x = struct.unpack_from('<d', d, i + 4)[0]
        largo = struct.unpack_from('<I', d, i + 13)[0]
        if 0 <= x <= 1 and largo <= 260:
            info = {'color': '#' + d[i:i + 3].hex().upper()}
            e = i + 17 + 2 * largo + 48
            if e + 8 <= len(d):
                esp = struct.unpack_from('<d', d, e)[0]
                if math.isfinite(esp) and .1 <= esp <= 10:
                    info['espesor'] = round(esp, 2)
            return info
    return None

def colores_de(path):
    """{material: {'color': '#RRGGBB', 'espesor': mm}} con lo elegido en Polyboard (.ocp o
    biblioteca .mat-boole). Tras el nombre vienen 16 bytes de identificador y luego el registro."""
    d = descomprimir(path)
    if d is None:
        return {}
    res = {}
    for o, t, fin in cadenas(d):
        if t in res or IMAGEN.search(t) or d[fin + 16:fin + 20] != b'\0\0\0\0':
            continue
        info = registro_tras(d, fin + 20, fin + 72)
        if info:
            res[t] = info
    return res

def buscar_material(fuentes, nombre):
    """Primera fuente que conoce el material: nombre exacto en todas y, si no, sin mayúsculas ni acentos.
    Polyboard distingue 'Blanco' (tablero) de 'blanco' (canto)."""
    for exacto in (True, False):
        for dic, origen in fuentes:
            if exacto:
                if nombre in dic:
                    return dic[nombre], origen
            else:
                k = clave(nombre)
                for n, v in dic.items():
                    if clave(n) == k and v:
                        return v, origen
    return None, None

class Texturas:
    """Resuelve material -> imagen y guarda una copia reducida en <salida>/texturas/."""
    def __init__(self, carpetas, biblioteca, salida, ocp):
        try:
            import PIL
        except ImportError:
            raise ErrorConversion("Para usar texturas hace falta Pillow:  pip install pillow") from None
        self.avisos = []
        self.carpetas = [Path(c) for c in carpetas if Path(c).is_dir()]
        for c in carpetas:
            if not Path(c).is_dir():
                self.avisos.append(f"no existe la carpeta de texturas {c}")
        self.salida = Path(salida)
        # índice de imágenes por nombre de archivo, para rutas que no coinciden exactamente
        self.por_nombre = {}
        for c in self.carpetas:
            for f in c.rglob('*'):
                if IMAGEN.search(f.name):
                    self.por_nombre.setdefault(f.name.lower(), f)
                    self.por_nombre.setdefault(f.stem.lower(), f)
        # fuentes en orden de prioridad: materiales.json, el .ocp del proyecto, bibliotecas de Polyboard
        self.forzados = {}
        mj = self.salida / 'materiales.json'
        if mj.exists():
            for k, v in json.loads(mj.read_text(encoding='utf-8')).items():
                if isinstance(v, str):
                    v = {'textura': v} if IMAGEN.search(v) else {'color': v}
                if isinstance(v, dict):
                    self.forzados[k] = v
        self.ocp, self.col_ocp = {}, {}
        for o in ([ocp] if isinstance(ocp, (str, Path)) else ocp):
            for k, v in texturas_de(o).items():
                self.ocp.setdefault(k, v)
            for k, v in colores_de(o).items():
                self.col_ocp.setdefault(k, v)
        self.tableros, self.cantos, self.col_tableros, self.col_cantos = {}, {}, {}, {}
        bib = Path(biblioteca) if biblioteca else None
        if bib and bib.is_dir():
            self.tableros = texturas_de(bib / 'Panel.mat-boole', True) if (bib / 'Panel.mat-boole').exists() else {}
            self.col_tableros = colores_de(bib / 'Panel.mat-boole') if (bib / 'Panel.mat-boole').exists() else {}
            self.col_cantos = colores_de(bib / 'Edge.mat-boole') if (bib / 'Edge.mat-boole').exists() else {}
            self.cantos = texturas_de(bib / 'Edge.mat-boole', True) if (bib / 'Edge.mat-boole').exists() else {}
        elif biblioteca:
            self.avisos.append(f"no se encontró la biblioteca de materiales {biblioteca}")

    def buscar(self, rel):
        """Ruta de Polyboard ('Egger\\x.jpg', relativa a Textures) -> archivo, o None."""
        rel = rel.replace('\\', '/')
        if Path(rel).is_absolute():
            return Path(rel) if Path(rel).exists() else None
        for c in self.carpetas:
            f = c / rel
            if f.exists():
                return f
        # distinta mayúscula/carpeta: buscar por nombre de archivo
        nombre = rel.rsplit('/', 1)[-1].lower()
        return self.por_nombre.get(nombre) or self.por_nombre.get(nombre.rsplit('.', 1)[0])

    def material(self, nombre, es_canto):
        f = self.forzados.get(nombre) or next((v for k, v in self.forzados.items() if clave(k) == clave(nombre)), {})
        info = {}
        if f.get('color'):
            info['color'] = f['color']
        if 'textura' in f:                         # "" o null en materiales.json: sin textura
            tex, origen = ((f['textura'], f.get('ancho')), 'materiales.json') if f['textura'] else (None, None)
        else:
            bib = [(self.cantos, 'biblioteca de cantos'), (self.tableros, 'biblioteca de tableros')]
            tex, origen = buscar_material([(self.ocp, '.ocp')] + (bib if es_canto else bib[::-1]), nombre)
        if tex:
            rel, ancho = tex
            archivo = self.buscar(rel)
            if archivo:
                info.update(self.procesar(archivo, ancho, 'color' not in info))
                info['origen'] = f"{origen}: {rel}"
            else:
                self.avisos.append(f"{nombre}: no se encontró la imagen {rel} ({origen})")
        # color (sin textura) y espesor (cantos) tal como están en Polyboard. En el .ocp solo el
        # nombre exacto: sin distinguir mayúsculas se confundirían tablero ('f-Tribal') y canto ('f-tribal')
        pb, origen = (self.col_ocp[nombre], '.ocp') if nombre in self.col_ocp else \
            buscar_material([(self.col_cantos if es_canto else self.col_tableros, 'biblioteca')], nombre)
        if pb:
            if 'color' not in info:
                info['color'] = pb['color']
                info.setdefault('origen', f"color de Polyboard ({origen})")
            if es_canto and pb.get('espesor'):
                info['espesor'] = pb['espesor']
        return info

    def procesar(self, archivo, ancho, con_color):
        """Copia de máx. 512 px con la veta horizontal (a lo largo del eje U), en potencias de 2
        para que se pueda repetir en cualquier celular. Devuelve textura, color y medidas en mm."""
        from PIL import Image, ImageChops, ImageStat
        im = Image.open(archivo)
        im = im.convert('RGBA').convert('RGB') if im.mode in ('P', 'LA', 'RGBA') else im.convert('RGB')
        w0, h0 = im.size
        mm_px = float(ancho or ANCHO_TEXTURA) / w0
        # dirección de la veta: las fibras cambian poco a lo largo y mucho a lo ancho
        g = im.convert('L'); g.thumbnail((256, 256))
        dx = ImageStat.Stat(ImageChops.difference(g.crop((1, 0, g.width, g.height)), g.crop((0, 0, g.width - 1, g.height)))).mean[0]
        dy = ImageStat.Stat(ImageChops.difference(g.crop((0, 1, g.width, g.height)), g.crop((0, 0, g.width, g.height - 1)))).mean[0]
        if dx > dy * 1.25 or (dy <= dx * 1.25 and h0 > w0):   # veta vertical (o dudosa en imagen alta)
            im = im.transpose(Image.Transpose.ROTATE_90)
        w, h = im.size
        k = min(1, 512 / max(w, h))
        pot = lambda n: 1 << max(4, min(9, round(math.log2(max(n, 1)))))
        chica = im.resize((pot(w * k), pot(h * k)), Image.LANCZOS)
        ruta = hashlib.md5(str(archivo).lower().encode()).hexdigest()[:6]
        nombre = re.sub(r'[^a-z0-9]+', '-', clave(archivo.stem)).strip('-')[:40] + '-' + ruta + '.jpg'
        (self.salida / 'texturas').mkdir(parents=True, exist_ok=True)
        chica.save(self.salida / 'texturas' / nombre, 'JPEG', quality=82, optimize=True)
        info = dict(textura=f"texturas/{nombre}")
        if con_color:
            r, gg, b = (round(x) for x in ImageStat.Stat(im.resize((64, 64))).mean[:3])
            info['color'] = f"#{r:02X}{gg:02X}{b:02X}"
        info['ancho'], info['alto'] = round(w * mm_px), round(h * mm_px)   # mm que cubre la imagen ya girada
        return info

def resolver_materiales(paneles, tex):
    """{nombre: {color, textura, ancho, alto}} de los materiales usados (tablero y cantos)."""
    usados = {}
    for p in paneles:
        if p['mat']:
            usados.setdefault(p['mat'], False)
        for c in p['cantos']:
            if c['mat']:
                usados[c['mat']] = usados.get(c['mat'], True)
    materiales = {}
    for nombre, es_canto in sorted(usados.items(), key=lambda x: clave(x[0])):
        info = tex.material(nombre, es_canto)
        estado = (f"textura {info['textura']}  ({info['origen']})" if info.get('textura')
                  else f"sin textura, {info['origen']}" if info.get('origen') else 'sin textura')
        log.info(f"Material {nombre!r}: {estado}" + (f"  color {info['color']}" if info.get('color') else '')
                 + (f"  espesor {info['espesor']} mm" if info.get('espesor') else ''))
        if info:
            info.pop('origen', None)
            materiales[nombre] = info
    return materiales

# ---------------------------------------------------------------- salida
def a_y_arriba(v):
    # DXF: Z arriba  ->  visor: Y arriba
    return [round(v[0], 1), round(v[2], 1), round(-v[1], 1)]

def tris_planos(caras):
    out = []
    for c in caras:
        a, b, cc, d = (a_y_arriba(v) for v in c)
        out += a + b + cc
        if d != cc:
            out += a + cc + d
    return out

def caja(caras):
    (x0, y0, z0), (x1, y1, z1) = bbox(caras)
    a, b = a_y_arriba((x0, y0, z0)), a_y_arriba((x1, y1, z1))
    return [min(a[i], b[i]) for i in range(3)] + [max(a[i], b[i]) for i in range(3)]

@dataclass
class Resultado:
    """Lo que devuelve convertir(): el proyecto, dónde quedó y qué conviene revisar."""
    proyecto: str
    archivo: Path            # <destino>/<proyecto>.json (versión del taller)
    codigo: str              # código de la versión del cliente: <destino>/clientes/<codigo>.json
    avisos: list = field(default_factory=list)
    resumen: dict = field(default_factory=dict)

def convertir(dxf, ocps, destino, texturas=None, *, biblioteca=None, codigo=None):
    """Convierte un proyecto de Polyboard para el visor.

    dxf: DXF 3D exportado de Polyboard. ocps: uno o varios .ocp (proyecto dividido en partes).
    destino: carpeta donde se escriben <proyecto>.json, clientes/<codigo>.json, clientes/<codigo>/*.glb
    y texturas/. texturas: carpetas Textures de Polyboard (opcional); biblioteca: carpeta Materials
    (por defecto, junto a la primera de texturas). codigo: código del link del cliente, o una función
    proyecto -> código, para conservar el link entre conversiones; si falta se inventa uno.
    Si el proyecto no se puede convertir, lanza ErrorConversion con un mensaje para el taller."""
    ocps = [ocps] if isinstance(ocps, (str, Path)) else list(ocps)
    if not ocps:
        raise ErrorConversion("Falta la lista de OptiCut (.ocp) del proyecto.")
    texturas = [texturas] if isinstance(texturas, (str, Path)) else list(texturas or [])
    piezas = []
    for ocp in ocps:     # un proyecto dividido en partes: se suman las piezas de todos los .ocp
        partes = leer_ocp(ocp)
        if len(ocps) > 1:
            log.info(f"OCP {Path(ocp).name}: {len(partes)} piezas")
        piezas += partes
    paneles, herrajes, muros, cuenta = leer_dxf(dxf)
    proyecto, avisos = vincular(piezas, paneles, cuenta)
    for p in paneles:
        p['mat'], p['cantos'] = materiales(p)
    if not proyecto or len(ocps) > 1:    # con varias partes, el nombre es el del DXF
        proyecto = Path(dxf).stem
    mats = {}
    if texturas:
        biblioteca = biblioteca or Path(texturas[0]).parent / 'Materials'
        tex = Texturas(texturas, biblioteca, destino, ocps)
        mats = resolver_materiales(paneles, tex)
        avisos += tex.avisos

    # identificador de cada pieza 3D: mueble + ruta de bloques del modelo de Polyboard (las dos puertas
    # de un par comparten nº de mecanizado pero no bloque). Estable mientras no cambie el modelo.
    vistos = {}
    for p in paneles:
        base_id = p['mueble'] + '|' + '/'.join(b.split('.', 1)[-1] for b in p['ruta'][1:])
        vistos[base_id] = vistos.get(base_id, 0) + 1
        p['id'] = base_id if vistos[base_id] == 1 else f"{base_id}#{vistos[base_id]}"
    muebles = sorted({p['mueble'] for p in paneles})
    datos = dict(
        proyecto=proyecto,
        muebles=muebles,
        paneles=[dict(id=p['id'], num=p['num'], pieza=p.get('pieza', ''), nombre=p.get('nombre_ocp', p['nombre']), mueble=p['mueble'],
                      med=[round(x, 1) for x in p['med']], cant=p.get('cant', 1),
                      mat=p['mat'], **({'vt': 1} if p.get('veta_cruzada') else {}),
                      cantos=[dict(mat=c['mat'], lado=c['lado'], largo=c['largo'], pos=c['pos'],
                                   v=[x for q in c['v'] for x in a_y_arriba(q)]) for c in p['cantos']],
                      tal=[a_y_arriba(h['c']) + [round(h['n'][0], 3), round(h['n'][2], 3), round(-h['n'][1], 3),
                           h['d'], h['prof'], round(h['vis'], 1), 1 if h['canto'] else 0] for h in p['taladros']],
                      t=tris_planos(p['caras'])) for p in paneles],
        herrajes=[dict(mueble=vincular_mueble, b=caja(h['caras']))
                  for h in herrajes
                  for vincular_mueble in [h['ruta'][0].split('.', 1)[-1] + (f"-{letra(h['inst'])}" if cuenta.get(h['ruta'][0], 1) > 1 else '')]],
        muros=[tris_planos(m['caras']) for m in muros],
    )
    if mats:
        datos['materiales'] = mats
    salida = Path(destino); salida.mkdir(parents=True, exist_ok=True)
    codigo = (codigo(proyecto) if callable(codigo) else codigo) or secrets.token_urlsafe(9)
    datos['cliente'] = codigo     # el taller ve el código para compartir el link
    avisos += version_cliente(datos, salida, codigo)
    archivo = salida / f"{proyecto}.json"
    archivo.write_text(json.dumps(datos, separators=(',', ':'), ensure_ascii=False), encoding='utf-8')

    resumen = dict(
        piezas_ocp=len(piezas),
        paneles=len(paneles),
        con_mecanizado=sum(1 for p in paneles if p['num']),
        piezas_con_numero=len({p['num'] for p in paneles if p['num']}),
        vinculados=sum(p['asignado'] for p in paneles),
        taladros=sum(len(p['taladros']) for p in paneles),
        herrajes=len(herrajes),
        muros=len(muros),
    )
    return Resultado(proyecto=proyecto, archivo=archivo, codigo=codigo, avisos=avisos, resumen=resumen)

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('dxf')
    ap.add_argument('ocp', nargs='+', help='uno o varios .ocp (si el proyecto se dividió en partes)')
    ap.add_argument('-o', '--salida', default='data')
    ap.add_argument('--texturas', action='append', metavar='CARPETA',
                    help='carpeta Textures de Polyboard (se puede repetir)')
    ap.add_argument('--biblioteca', metavar='CARPETA',
                    help='carpeta Materials con Panel.mat-boole y Edge.mat-boole (por defecto, junto a Textures)')
    ap.add_argument('--url', help='dirección pública del visor, para armar el link del cliente')
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format='%(message)s')
    log.setLevel(logging.INFO)

    # el código del cliente se conserva entre conversiones (data/.clientes.json, que el servidor no
    # publica), así el link ya enviado sigue andando con la versión nueva
    salida = Path(args.salida)
    mapa_path = salida / '.clientes.json'
    mapa = json.loads(mapa_path.read_text(encoding='utf-8')) if mapa_path.exists() else {}
    try:
        r = convertir(args.dxf, args.ocp, salida, args.texturas, biblioteca=args.biblioteca, codigo=mapa.get)
    except ErrorConversion as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    mapa[r.proyecto] = r.codigo
    mapa_path.write_text(json.dumps(mapa, ensure_ascii=False, indent=1), encoding='utf-8')

    idx_path = salida / 'index.json'
    idx = json.loads(idx_path.read_text(encoding='utf-8')) if idx_path.exists() else []
    idx = [x for x in idx if x['proyecto'] != r.proyecto] + [dict(proyecto=r.proyecto, archivo=r.archivo.name,
                                                                piezas=r.resumen['piezas_con_numero'])]
    idx_path.write_text(json.dumps(sorted(idx, key=lambda x: x['proyecto']), ensure_ascii=False, indent=1), encoding='utf-8')

    n = r.resumen
    print(f"Proyecto: {r.proyecto}")
    print(f"Taladros: {n['taladros']}")
    print(f"Paneles 3D: {n['paneles']}  (con mecanizado: {n['con_mecanizado']}, vinculados al .ocp: {n['vinculados']})  Herrajes: {n['herrajes']}  Muros: {n['muros']}")
    for a in r.avisos:
        print("AVISO:", a)
    print(f"Link para el cliente: {args.url.rstrip('/')}/?c={r.codigo}" if args.url else f"Código del cliente: {r.codigo}")
    return 0

# ---------------------------------------------------------------- modelo para AR (GLB)
# Mismos colores que el visor (index.html: colorMaterial) para los materiales sin textura.
COLORES_BASE = {
    'blanco': '#F4F4F0', 'negro': '#2A2C2E', 'grafito': '#4C4F52', 'gris humo': '#7D8083', 'gris': '#A2A6A9',
    'aluminio': '#BCC0C2', 'almendra': '#E6D9BF', 'lino': '#DCD5C6', 'arena': '#D8C7A5', 'cashmere': '#D3C6B5',
    'roble': '#BA8C5C', 'nogal': '#6F4D35', 'cedro': '#9C5D3E', 'haya': '#D3A77A', 'peral': '#C9966A',
    'wengue': '#4B372A', 'cerezo': '#9D5234', 'teka': '#A2693C', 'fresno': '#CFB590', 'olmo': '#AA8663',
    'pino': '#DAB97F', 'mdf': '#B58F63', 'crudo': '#B58F63', 'fibro': '#8E6B48', 'hardboard': '#8E6B48'}

def color_visor(nombre, mats, usuario):
    """Color de un material como lo muestra el visor: materiales.json > color del proyecto
    (textura o Polyboard) > palabra clave > color estable según el nombre."""
    import colorsys
    n = clave(nombre)
    u = usuario.get(nombre) or next((v for k, v in usuario.items() if clave(k) == n), None)
    info = mats.get(nombre) or next((v for k, v in mats.items() if clave(k) == n), {})
    c = u or info.get('color') or COLORES_BASE.get(n)
    if not c:
        k = next((k for k in sorted(COLORES_BASE, key=len, reverse=True) if k in n), None)
        c = COLORES_BASE[k] if k else None
    if not c:
        h = 0
        for ch in n:
            h = (h * 31 + ord(ch)) & 0xFFFFFFFF
        r, g, b = colorsys.hls_to_rgb((h % 360) / 360, .62, .28)
        c = '#%02X%02X%02X' % (round(r * 255), round(g * 255), round(b * 255))
    return c

def lineal(hex_):
    """Color #RRGGBB (sRGB, como se ve) a los valores lineales que espera glTF."""
    def f(v):
        v /= 255
        return v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4
    return [f(int(hex_[i:i + 2], 16)) for i in (1, 3, 5)] + [1.0]

def _resta(a, b): return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
def _cruz(a, b): return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
def _punto(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def _norm(a):
    l = math.sqrt(_punto(a, a)) or 1
    return [a[0] / l, a[1] / l, a[2] / l]

def glb_ar(datos, paneles, herrajes, salida_data, usuario, con_textura=True):
    """GLB (metros, apoyado en el piso y centrado) con las caras texturadas como en el visor (veta
    a lo largo del lado mayor, o del menor si 'vt'), cantos del color del tablero y herrajes.
    Una malla por material. Para Scene Viewer (Android) y AR Quick Look (iPhone)."""
    mats = datos.get('materiales', {})
    grupos = {}   # clave de material -> {'mat': dict glTF, 'img': ruta o None, 'pos': [], 'nor': [], 'uv': []}
    def grupo(k, color, img=None, metal=0.0, rugoso=.75):
        if k not in grupos:
            grupos[k] = dict(color=color, img=img, metal=metal, rugoso=rugoso, pos=[], nor=[], uv=[])
        return grupos[k]
    def tri(g, a, b, c, n, uv=((0, 0), (0, 0), (0, 0))):
        for v, t in zip((a, b, c), uv):
            g['pos'] += v; g['nor'] += n; g['uv'] += t
    for p in paneles:
        t = p['t']
        tris = []
        for i in range(0, len(t), 9):
            a, b, c = t[i:i + 3], t[i + 3:i + 6], t[i + 6:i + 9]
            n = _cruz(_resta(b, a), _resta(c, a))
            area = math.sqrt(_punto(n, n))
            if area > 0:
                tris.append((a, b, c, _norm(n), area))
        if not tris:
            continue
        big = max(tris, key=lambda x: x[4])
        lados = sorted((_resta(big[1], big[0]), _resta(big[2], big[1]), _resta(big[0], big[2])), key=lambda v: _punto(v, v))
        eL = _norm(lados[0] if p.get('vt') else lados[1]); eN = big[3]; eS = _norm(_cruz(eN, eL))
        info = mats.get(p['mat'], {})
        col = color_visor(p['mat'], mats, usuario)
        tex = info.get("textura") if con_textura else None
        aU = info.get('ancho') or 1000; aV = info.get('alto') or aU
        cara = grupo('tex:' + tex if tex else 'col:' + col, [1, 1, 1, 1] if tex else lineal(col), tex)
        canto = grupo('canto:' + col, lineal(info.get('color') or col))
        for a, b, c, n, _ in tris:
            if abs(_punto(n, eN)) > .9:
                tri(cara, a, b, c, n, [(_punto(v, eL) / aU, _punto(v, eS) / aV) for v in (a, b, c)])
            else:
                tri(canto, a, b, c, n)
    gh = grupo('herraje', lineal('#9AA3AA'), metal=.6, rugoso=.4)
    for h in herrajes:
        x0, y0, z0, x1, y1, z1 = h['b']
        q = [[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0], [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]]
        for i, j, k, l, n in ((0, 1, 2, 3, [0, 0, -1]), (5, 4, 7, 6, [0, 0, 1]), (4, 0, 3, 7, [-1, 0, 0]),
                              (1, 5, 6, 2, [1, 0, 0]), (3, 2, 6, 7, [0, 1, 0]), (4, 5, 1, 0, [0, -1, 0])):
            tri(gh, q[i], q[j], q[k], n); tri(gh, q[i], q[k], q[l], n)
    grupos = {k: g for k, g in grupos.items() if g['pos']}
    if not grupos:
        return None
    # milímetros -> metros, centrado y apoyado en el piso
    todas = [g['pos'] for g in grupos.values()]
    xs = [v for ps in todas for v in ps[0::3]]; ys = [v for ps in todas for v in ps[1::3]]; zs = [v for ps in todas for v in ps[2::3]]
    cx, cy, cz = (min(xs) + max(xs)) / 2, min(ys), (min(zs) + max(zs)) / 2
    binario, vistas, accesores, mallas, materiales, imagenes, texturas, img_idx = bytearray(), [], [], [], [], [], [], {}
    def vista(datos_b):
        while len(binario) % 4:
            binario.append(0)
        vistas.append(dict(buffer=0, byteOffset=len(binario), byteLength=len(datos_b)))
        binario.extend(datos_b)
        return len(vistas) - 1
    def accesor(valores, tipo, minmax=False):
        n = {'VEC3': 3, 'VEC2': 2}[tipo]
        acc = dict(bufferView=vista(struct.pack(f'<{len(valores)}f', *valores)), componentType=5126,
                   count=len(valores) // n, type=tipo)
        if minmax:
            acc['min'] = [min(valores[i::n]) for i in range(n)]; acc['max'] = [max(valores[i::n]) for i in range(n)]
        accesores.append(acc)
        return len(accesores) - 1
    primitivas = []
    for g in grupos.values():
        pos = []
        for i in range(0, len(g['pos']), 3):
            pos += [(g['pos'][i] - cx) / 1000, (g['pos'][i + 1] - cy) / 1000, (g['pos'][i + 2] - cz) / 1000]
        m = dict(pbrMetallicRoughness=dict(baseColorFactor=g['color'], metallicFactor=g['metal'], roughnessFactor=g['rugoso']),
                 doubleSided=True)
        atributos = dict(POSITION=accesor(pos, 'VEC3', True), NORMAL=accesor(g['nor'], 'VEC3'))
        # índices explícitos (0..n-1): el formato no los exige, pero algunos visores de AR sí
        nv = len(pos) // 3
        corto = nv <= 65535
        vistas_idx = vista(struct.pack(f"<{nv}{'H' if corto else 'I'}", *range(nv)))
        accesores.append(dict(bufferView=vistas_idx, componentType=5123 if corto else 5125, count=nv, type='SCALAR'))
        indices = len(accesores) - 1
        if g['img']:
            if g['img'] not in img_idx:
                archivo = Path(salida_data) / g['img']
                if archivo.exists():
                    imagenes.append(dict(bufferView=vista(archivo.read_bytes()), mimeType='image/jpeg'))
                    texturas.append(dict(sampler=0, source=len(imagenes) - 1))
                    img_idx[g['img']] = len(texturas) - 1
            if g['img'] in img_idx:
                m['pbrMetallicRoughness']['baseColorTexture'] = dict(index=img_idx[g['img']])
                atributos['TEXCOORD_0'] = accesor(g['uv'], 'VEC2')
        materiales.append(m)
        primitivas.append(dict(attributes=atributos, indices=indices, material=len(materiales) - 1))
    doc = dict(asset=dict(version='2.0', generator='polyboard_a_app'), scene=0, scenes=[dict(nodes=[0])],
               nodes=[dict(mesh=0, name=datos['proyecto'])], meshes=[dict(primitives=primitivas)],
               materials=materiales, accessors=accesores, bufferViews=vistas, buffers=[dict(byteLength=len(binario))])
    if imagenes:
        doc.update(images=imagenes, textures=texturas, samplers=[dict(magFilter=9729, minFilter=9987, wrapS=10497, wrapT=10497)])
    js = json.dumps(doc, separators=(',', ':')).encode()
    js += b' ' * (-len(js) % 4)
    binario += b'\0' * (-len(binario) % 4)
    total = 12 + 8 + len(js) + 8 + len(binario)
    return (struct.pack('<III', 0x46546C67, 2, total) + struct.pack('<II', len(js), 0x4E4F534A) + js
            + struct.pack('<II', len(binario), 0x004E4942) + bytes(binario))

def version_cliente(datos, salida, codigo):
    """<salida>/clientes/<codigo>.json: solo geometría y materiales, sin números, taladros ni nombres
    de piezas, y los modelos de AR en clientes/<codigo>/. Devuelve los avisos."""
    avisos = []
    cliente = dict(
        proyecto=datos['proyecto'],
        muebles=datos['muebles'],
        paneles=[dict(mueble=p['mueble'], mat=p['mat'], **({'vt': 1} if p.get('vt') else {}),
                      cantos=[dict(mat=c['mat'], v=c['v']) for c in p['cantos'] if c['mat']],
                      t=p['t']) for p in datos['paneles']],
        herrajes=datos['herrajes'],
        muros=datos['muros'],
    )
    if 'materiales' in datos:
        cliente['materiales'] = datos['materiales']
    (salida / 'clientes').mkdir(exist_ok=True)
    # modelos de AR (Scene Viewer necesita un archivo publicado): el proyecto completo y cada mueble
    try:
        mj = salida / 'materiales.json'
        usuario = {k: (v if isinstance(v, str) else v.get('color')) for k, v in
                   (json.loads(mj.read_text(encoding='utf-8')).items() if mj.exists() else [])}
        usuario = {k: v for k, v in usuario.items() if isinstance(v, str) and re.fullmatch(r'#[0-9A-Fa-f]{6}', v)}
        carpeta_ar = salida / 'clientes' / codigo
        carpeta_ar.mkdir(exist_ok=True)
        for f in carpeta_ar.glob('*.glb'):
            f.unlink()
        ar = {}
        for i, mueble in enumerate([None] + datos['muebles']):
            pan = [p for p in datos['paneles'] if mueble is None or p['mueble'] == mueble]
            her = [h for h in datos['herrajes'] if mueble is None or h['mueble'] == mueble]
            glb = glb_ar(datos, pan, her, salida, usuario)
            if glb:
                nombre = 'todo.glb' if mueble is None else f'mueble-{i}.glb'
                (carpeta_ar / nombre).write_bytes(glb)
                ar[mueble or ''] = f'{codigo}/{nombre}'
        cliente['ar'] = ar
    except Exception as e:   # sin AR nativa: el visor arma el modelo en el celular
        avisos.append(f"no se pudieron generar los modelos de AR: {e}")
    (salida / 'clientes' / f"{codigo}.json").write_text(
        json.dumps(cliente, separators=(',', ':'), ensure_ascii=False), encoding='utf-8')
    return avisos

if __name__ == '__main__':
    sys.exit(main())
