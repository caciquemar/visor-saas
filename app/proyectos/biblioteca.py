"""Importar la biblioteca de materiales de Polyboard (Panel.mat-boole y Edge.mat-boole) a Materiales.

En el servidor no están las bibliotecas de Polyboard, y el .ocp de un proyecto no siempre trae el color o la textura
de cada material (f-Tribal tiene su color solo en la biblioteca; f-Yute, su textura). El taller sube las dos
bibliotecas y acá se cargan sus tableros y cantos: con textura, la ruta y el ancho (la imagen se sube después, desde
la carpeta Textures, en la misma pantalla); sin textura, el color. Un material tiene textura o color, no los dos.
Lo que el taller ya cargó no se pisa: la imagen nunca, y el color solo si lo pide.
"""
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from django.db import IntegrityError, transaction

from conversor.polyboard_a_app import clave, colores_de, texturas_de

from .models import Material


SEPARADOR = re.compile(r'-{3,}')     # "B----Blancos", "e-----egger-----": títulos de la lista en Polyboard


@dataclass
class Resultado:
    nuevos: int = 0
    cambiados: int = 0
    iguales: int = 0

    @property
    def total(self):
        return self.nuevos + self.cambiados + self.iguales


def leer(archivo):
    """{nombre: {'textura': (ruta, ancho o None)} o {'color': '#RRGGBB'}} de un .mat-boole subido. Solo los
    materiales de verdad: con un registro de color o con una imagen."""
    with tempfile.TemporaryDirectory() as tmp:
        ruta = Path(tmp) / 'biblioteca.mat-boole'
        with open(ruta, 'wb') as f:
            for trozo in archivo.chunks():
                f.write(trozo)
        texturas, colores = texturas_de(ruta), colores_de(ruta)
    materiales = {}
    for nombre in sorted(set(texturas) | set(colores)):
        if SEPARADOR.search(nombre):
            continue
        if texturas.get(nombre):
            materiales[nombre] = {'textura': texturas[nombre]}
        elif (colores.get(nombre) or {}).get('color'):
            materiales[nombre] = {'color': colores[nombre]['color'].upper()}
    return materiales


def importar(materiales, tipo, reemplazar_colores=False):
    """Carga en la biblioteca del taller lo que devolvió `leer`. Devuelve cuántos sumó, cambió y dejó igual."""
    res = Resultado()
    existentes = {m.clave: m for m in Material.objects.filter(tipo=tipo)}
    for nombre, info in materiales.items():
        m = existentes.get(clave(nombre))
        if m is None:
            m = Material(tipo=tipo, nombre=nombre)
            completar(m, info, reemplazar_colores)
            try:
                with transaction.atomic():
                    m.save()
            except IntegrityError:                # dos nombres que se escriben igual sin mayúsculas ni acentos
                res.iguales += 1
                continue
            existentes[m.clave] = m
            res.nuevos += 1
        elif completar(m, info, reemplazar_colores):
            m.save()
            res.cambiados += 1
        else:
            res.iguales += 1
    return res


def completar(m, info, reemplazar_colores):
    """Pone en el material lo que le falta de la biblioteca. Devuelve si cambió algo."""
    antes = (m.ruta_polyboard, m.ancho_mm, m.color)
    if 'textura' in info:
        ruta, ancho = info['textura']
        if not m.ruta_polyboard:
            m.ruta_polyboard = ruta[:300]
        if not m.ancho_mm and ancho:
            m.ancho_mm = round(ancho)
    elif not m.textura and (not m.color or reemplazar_colores):
        m.color = info['color']
    return (m.ruta_polyboard, m.ancho_mm, m.color) != antes


def faltan_imagenes():
    """Los materiales con la ruta de su imagen en Polyboard y sin imagen subida: lo que la pantalla busca en la
    carpeta Textures. [{id, nombre, tipo, ruta}]"""
    return [{'id': m.pk, 'nombre': m.nombre, 'tipo': m.get_tipo_display().lower(), 'ruta': m.ruta_polyboard}
            for m in Material.objects.exclude(ruta_polyboard='').filter(textura='').order_by('tipo', 'clave')]
