"""PDF de etiquetas con QR, para hoja A4 de etiquetas autoadhesivas o para rollo de impresora térmica.

No depende de Django: recibe los datos ya armados (ver `etiqueta_de_pieza` y `etiqueta_de_mueble`) y un `Formato`.
El QR lleva solo la dirección de la etiqueta; todo lo demás va impreso como texto.
"""
import io
import math
from dataclasses import dataclass

from reportlab.graphics.barcode.qrencoder import QRCode, QRErrorCorrectLevel
from reportlab.lib.colors import Color, black, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

GRIS = Color(.38, .38, .38)
GRIS_CLARO = Color(.75, .75, .75)


@dataclass
class Formato:
    """Medidas en mm. Hoja: `columnas` × `filas` etiquetas de `ancho` × `alto` en A4, desde los márgenes, con
    `sep_h` y `sep_v` entre etiquetas. Rollo: una etiqueta por página de `ancho` × `alto`; los márgenes corren el
    dibujo (para corregir la impresora)."""
    tipo: str               # 'hoja' o 'rollo'
    ancho: float
    alto: float
    columnas: int = 1
    filas: int = 1
    margen_sup: float = 0
    margen_izq: float = 0
    sep_h: float = 0
    sep_v: float = 0
    bordes: bool = False    # línea de corte alrededor de cada etiqueta (para probar en papel común)
    esquema: str = 'mueble'  # en la del mueble: 'mueble', 'proyecto' (con el mueble marcado) o 'ninguno'

    @property
    def por_hoja(self):
        return self.columnas * self.filas if self.tipo == 'hoja' else 1


# Formatos comunes de hojas A4 autoadhesivas y de rollos térmicos.
FORMATOS = {
    'a4-3x8': Formato('hoja', 70, 37, 3, 8, margen_sup=0.5, margen_izq=0),
    'a4-3x7': Formato('hoja', 63.5, 38.1, 3, 7, margen_sup=15.15, margen_izq=7.2, sep_h=2.5),
    'a4-2x7': Formato('hoja', 99.1, 38.1, 2, 7, margen_sup=15.15, margen_izq=4.65, sep_h=2.5),
    'a4-2x4': Formato('hoja', 99.1, 67.7, 2, 4, margen_sup=13, margen_izq=4.65, sep_h=2.5),
    'rollo-100x50': Formato('rollo', 100, 50),
    'rollo-62x40': Formato('rollo', 62, 40),
}


def etiqueta_de_pieza(panel, proyecto, url, copia=1, de=1):
    """Datos impresos de una pieza (`panel` de proyecto.json)."""
    largo, ancho, esp = panel['med']
    return {'tipo': 'pieza', 'url': url, 'num': panel['num'], 'nombre': panel['nombre'], 'mueble': panel['mueble'],
            'proyecto': proyecto, 'largo': largo, 'ancho': ancho, 'esp': esp, 'tablero': panel.get('mat', ''),
            'cantos': [c for c in panel.get('cantos', [])], 'veta_cruzada': bool(panel.get('vt')),
            'copia': copia, 'de': de}


def etiqueta_de_mueble(mueble, proyecto, url, piezas, bulto=1, bultos=1, cliente='', direccion='', esquema=None):
    """`esquema`: las cajas de etiquetas/esquema.py (el mueble de frente, o el proyecto con el mueble marcado)."""
    return {'tipo': 'mueble', 'url': url, 'mueble': mueble, 'proyecto': proyecto, 'piezas': piezas,
            'bulto': bulto, 'bultos': bultos, 'cliente': cliente, 'direccion': direccion, 'esquema': esquema or []}


def generar(etiquetas, formato, desde=1):
    """El PDF (bytes). `desde`: en hoja, la primera etiqueta libre (1 = arriba a la izquierda), para aprovechar una
    hoja empezada."""
    buf = io.BytesIO()
    if formato.tipo == 'hoja':
        c = Canvas(buf, pagesize=A4)
        alto_hoja = A4[1]
        lugar = max(desde, 1) - 1
        for e in etiquetas:
            if lugar >= formato.por_hoja:
                c.showPage(); lugar = 0
            col, fila = lugar % formato.columnas, lugar // formato.columnas
            x = (formato.margen_izq + col * (formato.ancho + formato.sep_h)) * mm
            y = alto_hoja - (formato.margen_sup + (fila + 1) * formato.alto + fila * formato.sep_v) * mm
            _dibujar(c, e, x, y, formato.ancho * mm, formato.alto * mm, formato.bordes)
            lugar += 1
    else:
        c = Canvas(buf, pagesize=(formato.ancho * mm, formato.alto * mm))
        for i, e in enumerate(etiquetas):
            if i:
                c.showPage()
            _dibujar(c, e, formato.margen_izq * mm, -formato.margen_sup * mm, formato.ancho * mm,
                     formato.alto * mm, formato.bordes)
    c.setTitle('Etiquetas'); c.setCreator('Visor')
    c.save()
    return buf.getvalue()


# ---------- dibujo ----------

def _dibujar(c, e, x, y, w, h, bordes):
    c.saveState()
    if bordes:
        c.setStrokeColor(GRIS_CLARO); c.setLineWidth(.3); c.setDash(2, 2)
        c.rect(x, y, w, h); c.setDash()
    m = min(w, h) * .06                                   # margen interno: la troqueladora no es exacta
    (_pieza if e['tipo'] == 'pieza' else _mueble)(c, e, x + m, y + m, w - 2 * m, h - 2 * m)
    c.restoreState()


def _qr(c, url, x, y, lado, margen=2):
    """QR con corrección M y `margen` módulos de margen blanco a cada lado (el resto lo da el margen de la
    etiqueta). Todos los módulos negros van en UN solo trazado relleno: así no quedan rayitas blancas entre
    módulos vecinos al imprimir, y los blancos no se achican (con la tinta que corre de la térmica ya alcanza)."""
    q = QRCode(None, QRErrorCorrectLevel.M)
    q.addData(url); q.make()
    n = q.getModuleCount()
    m = lado / (n + 2 * margen)
    c.setFillColor(black)
    p = c.beginPath()
    for f in range(n):
        for a, b in _tramos([q.isDark(f, k) for k in range(n)]):
            p.rect(x + (a + margen) * m, y + lado - (f + 1 + margen) * m, (b - a) * m, m)
    c.drawPath(p, stroke=0, fill=1, fillMode=1)       # 1 = nonzero: los rectángulos que se tocan se unen


def _tramos(oscuros):
    """[(desde, hasta)] de los módulos oscuros seguidos de una fila o columna."""
    salida, ini = [], None
    for i, o in enumerate(oscuros + [False]):
        if o and ini is None:
            ini = i
        elif not o and ini is not None:
            salida.append((ini, i)); ini = None
    return salida


def _texto(c, s, x, y, ancho, fuente, tam, color=black, minimo=None):
    """Escribe `s` en una línea: achica la letra hasta `minimo` y, si igual no entra, corta con '…'."""
    minimo = minimo or tam * .7
    while tam > minimo and stringWidth(s, fuente, tam) > ancho:
        tam -= .25
    if stringWidth(s, fuente, tam) > ancho:
        while s and stringWidth(s + '…', fuente, tam) > ancho:
            s = s[:-1]
        s = s.rstrip() + '…'
    c.setFont(fuente, tam); c.setFillColor(color)
    c.drawString(x, y, s)
    return tam


def _mm(v):
    v = round(v, 1)
    return f'{v:g}'.replace('.', ',')


def _pieza(c, e, x, y, w, h):
    lado = min(h, w * .36)
    _qr(c, e['url'], x, y + (h - lado) / 2, lado)
    tx = x + lado + h * .04
    tw = x + w - tx
    u = h / 30                                            # unidad: las letras crecen con la etiqueta
    top = y + h
    # arriba, a todo el ancho: número grande (o "s/n") y copia
    num = e['num'] or 's/n'
    t = _texto(c, num, tx, top - 6.2 * u, tw * .6, 'Helvetica-Bold', 7.5 * u)
    if e['de'] > 1:
        _texto(c, f"{e['copia']} de {e['de']}", tx + stringWidth(num, 'Helvetica-Bold', t) + 1.4 * u,
               top - 6.2 * u, tw * .38, 'Helvetica-Bold', 3.6 * u)
    _texto(c, e['nombre'], tx, top - 10.6 * u, tw, 'Helvetica-Bold', 3.6 * u)
    _texto(c, e['mueble'], tx, top - 14.8 * u, tw, 'Helvetica', 3.1 * u)
    # abajo: textos a la izquierda y el dibujo de la pieza a la derecha
    dw = tw * .44
    iw = tw - dw - 1 * u
    _texto(c, e['proyecto'], tx, top - 18.4 * u, iw, 'Helvetica', 2.7 * u, GRIS)
    _texto(c, f"{_mm(e['largo'])} × {_mm(e['ancho'])}", tx, top - 23.2 * u, iw, 'Helvetica-Bold', 3.8 * u)
    _texto(c, f"esp. {_mm(e['esp'])}  {e['tablero']}", tx, top - 27 * u, iw, 'Helvetica', 2.7 * u, GRIS)
    _dibujo_pieza(c, e, x + w - dw, y, dw, h - 16 * u, u)


def _lados(cantos):
    """Para el dibujo: qué canto va en cada lado del rectángulo (abajo y arriba = lados largos, izquierda y
    derecha = lados cortos). Solo si la pieza es un rectángulo (4 lados); si no, None."""
    if len(cantos) != 4:
        return None
    primero = {'frente': 0, 'abajo': 1, 'izquierda': 2, 'atrás': 3, 'arriba': 4, 'derecha': 5}
    largos = sorted([k for k in cantos if k['lado'] == 'largo'], key=lambda k: primero.get(k['pos'], 9))
    cortos = sorted([k for k in cantos if k['lado'] == 'ancho'], key=lambda k: primero.get(k['pos'], 9))
    if len(largos) != 2 or len(cortos) != 2:
        return None
    return {'abajo': largos[0], 'arriba': largos[1], 'izquierda': cortos[0], 'derecha': cortos[1]}


def _dibujo_pieza(c, e, x, y, w, h, u):
    if h < 5 * u:
        return
    lados = _lados(e['cantos'])
    letra = 2.3 * u
    pad = letra * 1.25                                    # lugar para el nombre del canto en cada lado
    disp_w, disp_h = w - 2 * pad, h - 2 * pad
    # a escala, pero sin que una pieza muy angosta quede como una raya
    ratio = max(e['ancho'] / e['largo'], .28) if e['largo'] else 1
    rw = disp_w; rh = rw * ratio
    if rh > disp_h:
        rh = disp_h; rw = min(disp_w, rh / ratio)
    rx = x + pad + (disp_w - rw) / 2
    ry = y + pad + (disp_h - rh) / 2
    c.setFillColor(white)
    c.setStrokeColor(GRIS_CLARO); c.setLineWidth(.4)
    c.rect(rx, ry, rw, rh, stroke=1, fill=1)
    # cantos: lado grueso y su nombre afuera
    if lados:
        segs = {'abajo': (rx, ry, rx + rw, ry), 'arriba': (rx, ry + rh, rx + rw, ry + rh),
                'izquierda': (rx, ry, rx, ry + rh), 'derecha': (rx + rw, ry, rx + rw, ry + rh)}
        for donde, k in lados.items():
            if not k.get('mat'):
                continue
            c.setStrokeColor(black); c.setLineWidth(max(1.6, .55 * u)); c.setLineCap(0)
            c.line(*segs[donde])
            c.setFillColor(black)
            nombre = k['mat']
            if donde in ('abajo', 'arriba'):
                ty = ry - letra * 1.05 if donde == 'abajo' else ry + rh + letra * .3
                _texto_centrado(c, nombre, rx + rw / 2, ty, rw, letra)
            else:
                c.saveState()
                cx = rx - letra * .35 if donde == 'izquierda' else rx + rw + letra * 1.05
                c.translate(cx, ry + rh / 2); c.rotate(90)
                _texto_centrado(c, nombre, 0, 0, rh + 2 * pad, letra)
                c.restoreState()
    elif any(k.get('mat') for k in e['cantos']):
        mats = sorted({k['mat'] for k in e['cantos'] if k.get('mat')})
        _texto_centrado(c, 'cantos: ' + ', '.join(mats), rx + rw / 2, ry - letra * 1.05, w, letra)
    # veta: flecha doble a lo largo del lado mayor (o del menor si es cruzada)
    c.setStrokeColor(GRIS); c.setFillColor(GRIS); c.setLineWidth(max(.6, .22 * u))
    cx, cy = rx + rw / 2, ry + rh / 2
    if e['veta_cruzada']:
        l = rh * .32; _flecha(c, cx, cy - l, cx, cy + l, u)
    else:
        l = rw * .3; _flecha(c, cx - l, cy, cx + l, cy, u)


def _texto_centrado(c, s, cx, y, ancho, tam):
    while tam > 3 and stringWidth(s, 'Helvetica', tam) > ancho:
        tam -= .25
    if stringWidth(s, 'Helvetica', tam) > ancho:
        while s and stringWidth(s + '…', 'Helvetica', tam) > ancho:
            s = s[:-1]
        s += '…'
    c.setFont('Helvetica', tam)
    c.drawCentredString(cx, y, s)


def _flecha(c, x0, y0, x1, y1, u):
    c.line(x0, y0, x1, y1)
    a = math.atan2(y1 - y0, x1 - x0); p = 1.4 * u
    for (px, py, ang) in ((x1, y1, a), (x0, y0, a + math.pi)):
        pa = c.beginPath()
        pa.moveTo(px, py)
        pa.lineTo(px - p * math.cos(ang - .45), py - p * math.sin(ang - .45))
        pa.lineTo(px - p * math.cos(ang + .45), py - p * math.sin(ang + .45))
        pa.close()
        c.drawPath(pa, stroke=0, fill=1)


def _mueble(c, e, x, y, w, h):
    """Lo primero que se lee es el proyecto; después el mueble, y el bulto más chico. El QR, lo más grande posible
    (a lo alto de la etiqueta), con margen blanco amplio: se lee con la cámara del celular sobre el mueble. El
    esquema va a la derecha solo en etiquetas grandes, donde igual queda lugar para el texto."""
    u = h / 30
    lado = min(h, w * .42)
    if e.get('esquema'):
        dw, lado_con = min(w * .22, h * .9), min(h * .8, w * .36)
        queda = w - lado_con - dw - 2 * h * .05
        # con dibujo (y el QR un poco más chico) solo si el proyecto y el mueble entran enteros y grandes
        if (queda >= 30 * mm and stringWidth(e['proyecto'], 'Helvetica-Bold', 5.2 * u) <= queda
                and stringWidth(e['mueble'], 'Helvetica-Bold', 3.2 * u) <= queda):
            _esquema(c, e['esquema'], x + w - dw, y, dw, h)
            w -= dw + h * .05
            lado = lado_con
    _qr(c, e['url'], x, y + (h - lado) / 2, lado, margen=3)
    tx = x + lado + h * .04
    tw = x + w - tx
    top = y + h
    # el proyecto, lo más grande: en un renglón y, si no entra, en dos (nunca cortado si se puede evitar)
    if stringWidth(e['proyecto'], 'Helvetica-Bold', 5 * u) <= tw:
        _texto(c, e['proyecto'], tx, top - 6 * u, tw, 'Helvetica-Bold', 7 * u)
        yy = top - 11.8 * u
    else:
        uno, dos, tam = _partir(e['proyecto'], 'Helvetica-Bold', 5 * u, 3.6 * u, tw)
        _texto(c, uno, tx, top - 4.6 * u, tw, 'Helvetica-Bold', tam, minimo=tam)
        _texto(c, dos, tx, top - 9.6 * u, tw, 'Helvetica-Bold', tam, minimo=tam)
        yy = top - 14.4 * u
    _texto(c, e['mueble'], tx, yy, tw, 'Helvetica', 3.8 * u, minimo=3 * u)
    # bulto y piezas: chico (sin bultos: la etiqueta del mueble armado, ficha 18)
    bulto = f"Bulto {e['bulto']} de {e['bultos']}" if e['bultos'] else 'Mueble armado'
    _texto(c, f"{bulto} · {e['piezas']} piezas", tx, yy - 5 * u, tw, 'Helvetica', 3.3 * u, minimo=2.6 * u)
    abajo = [t for t in (e['cliente'], e['direccion']) if t][:2 if yy > top - 13 * u else 1]
    for k, t in enumerate(reversed(abajo)):
        _texto(c, t, tx, y + .6 * u + k * 4 * u, tw, 'Helvetica', 3 * u, GRIS, minimo=2.4 * u)


def _partir(s, fuente, tam, minimo, ancho):
    """`s` en dos renglones del mismo tamaño de letra: el más grande (de `tam` a `minimo`) en que entra todo,
    cortando entre palabras. Si ni así entra, el segundo renglón se corta al escribirlo. (uno, dos, tamaño)."""
    palabras = s.split()
    cortes = [(' '.join(palabras[:k]), ' '.join(palabras[k:])) for k in range(1, len(palabras))] or [(s, '')]
    while True:
        for uno, dos in cortes:
            if stringWidth(uno, fuente, tam) <= ancho and stringWidth(dos, fuente, tam) <= ancho:
                return uno, dos, tam
        if tam <= minimo:
            uno, dos = max(cortes, key=lambda c: stringWidth(c[0], fuente, tam) <= ancho and len(c[0]))
            return uno, dos, tam
        tam = max(minimo, tam - .25)


def _esquema(c, cajas, x, y, w, h):
    """El mueble de frente (o el proyecto con el mueble marcado), escalado para entrar en el rectángulo. Cada pieza es
    la caja de su proyección, de atrás hacia adelante: lo de adelante tapa. Solo el mueble: piezas blancas con borde
    negro. Con el proyecto: lo demás blanco con borde gris claro y el mueble en gris con borde negro (se ve igual en
    blanco y negro y en térmica)."""
    u0 = min(k['caja'][0] for k in cajas); v0 = min(k['caja'][1] for k in cajas)
    u1 = max(k['caja'][2] for k in cajas); v1 = max(k['caja'][3] for k in cajas)
    if u1 - u0 <= 0 or v1 - v0 <= 0:
        return
    escala = min(w / (u1 - u0), h / (v1 - v0))
    ox = x + (w - (u1 - u0) * escala) / 2
    oy = y + (h - (v1 - v0) * escala) / 2
    solo = all(k['del_mueble'] for k in cajas)
    marcado = Color(.78, .78, .78)
    for k in cajas:
        a, b, cc, d = k['caja']
        if k['del_mueble'] and not solo:
            c.setFillColor(marcado); c.setStrokeColor(black); c.setLineWidth(.45)
        elif k['del_mueble']:
            c.setFillColor(white); c.setStrokeColor(black); c.setLineWidth(.35)
        else:
            c.setFillColor(white); c.setStrokeColor(GRIS_CLARO); c.setLineWidth(.25)
        c.rect(ox + (a - u0) * escala, oy + (b - v0) * escala, max((cc - a) * escala, .2), max((d - b) * escala, .2),
               stroke=1, fill=1)
