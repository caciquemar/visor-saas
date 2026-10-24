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


def etiqueta_de_mueble(mueble, proyecto, url, piezas, bulto=1, bultos=1, cliente='', direccion=''):
    return {'tipo': 'mueble', 'url': url, 'mueble': mueble, 'proyecto': proyecto, 'piezas': piezas,
            'bulto': bulto, 'bultos': bultos, 'cliente': cliente, 'direccion': direccion}


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


def _qr(c, url, x, y, lado):
    """QR con corrección M y 2 módulos de margen blanco (el resto lo da el margen de la etiqueta). Se
    dibuja en tramos negros que se pisan un poco: módulo por módulo quedan rayitas blancas al imprimir."""
    q = QRCode(None, QRErrorCorrectLevel.M)
    q.addData(url); q.make()
    n = q.getModuleCount()
    m = lado / (n + 4)
    c.setFillColor(black)
    solapa = .06 * m
    for f in range(n):                                    # tramos por fila y por columna: tapan las costuras
        for tramo in _tramos([q.isDark(f, k) for k in range(n)]):
            c.rect(x + (tramo[0] + 2) * m - solapa, y + lado - (f + 3) * m - solapa,
                   (tramo[1] - tramo[0]) * m + 2 * solapa, m + 2 * solapa, stroke=0, fill=1)
    for k in range(n):
        for tramo in _tramos([q.isDark(f, k) for f in range(n)]):
            c.rect(x + (k + 2) * m - solapa, y + lado - (tramo[1] + 2) * m - solapa,
                   m + 2 * solapa, (tramo[1] - tramo[0]) * m + 2 * solapa, stroke=0, fill=1)


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
    lado = min(h, w * .4)
    _qr(c, e['url'], x, y + (h - lado) / 2, lado)
    tx = x + lado + h * .06
    tw = x + w - tx
    u = h / 30
    top = y + h
    _texto(c, e['proyecto'] + (f" · {e['cliente']}" if e['cliente'] else ''), tx, top - 3.4 * u, tw,
           'Helvetica', 3 * u, GRIS)
    _texto(c, e['mueble'], tx, top - 9.6 * u, tw, 'Helvetica-Bold', 5.4 * u, minimo=3.4 * u)
    # bulto, recuadrado para que se vea de lejos (sin bultos: la etiqueta del mueble armado, ficha 18)
    bulto = f"Bulto {e['bulto']} de {e['bultos']}" if e['bultos'] else 'Mueble armado'
    tb = 5 * u
    bw = stringWidth(bulto, 'Helvetica-Bold', tb) + 2.4 * u
    by = top - 18.4 * u
    c.setFillColor(black); c.roundRect(tx, by - 1.3 * u, min(bw, tw), tb + 1.9 * u, .8 * u, stroke=0, fill=1)
    _texto(c, bulto, tx + 1.2 * u, by, tw - 2.4 * u, 'Helvetica-Bold', tb, white)
    _texto(c, f"{e['piezas']} piezas", tx, by - 6 * u, tw, 'Helvetica', 3.2 * u)
    if e['direccion']:
        _texto(c, e['direccion'], tx, by - 10.2 * u, tw, 'Helvetica', 3 * u, GRIS)
