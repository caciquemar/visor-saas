"""Etiquetas con QR de piezas y muebles (ficha 12). El QR lleva solo /<taller>/e/<código>; el código apunta a una
clave (etiquetas/claves.py) del proyecto, no a una versión: al subir una versión nueva la etiqueta impresa abre la
misma pieza si sigue estando, o avisa que ya no está."""
import hashlib
import json
import secrets

from django.db import IntegrityError, models, transaction

from proyectos.models import Proyecto
from talleres.separacion import DatoDeTaller

from .pdf import FORMATOS

ALFABETO = '23456789ABCDEFGHJKMNPQRSTUVWXYZ'      # sin 0/O, 1/I/L: se puede leer en voz alta o escribir a mano
LARGO = 8


def codigo_nuevo():
    return ''.join(secrets.choice(ALFABETO) for _ in range(LARGO))


def huella(clave):
    return hashlib.sha256(json.dumps(clave, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Etiqueta(DatoDeTaller):
    class Tipo(models.TextChoices):
        PIEZA = 'pieza', 'Pieza'
        MUEBLE = 'mueble', 'Mueble'

    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name='etiquetas')
    tipo = models.CharField('tipo', max_length=6, choices=Tipo.choices)
    clave = models.JSONField('clave')
    huella = models.CharField(max_length=64, editable=False)
    codigo = models.CharField('código', max_length=LARGO, unique=True, editable=False)
    creada = models.DateTimeField('creada', auto_now_add=True)

    class Meta:
        verbose_name = 'etiqueta'
        verbose_name_plural = 'etiquetas'
        constraints = [models.UniqueConstraint(fields=['proyecto', 'tipo', 'huella'], name='una_etiqueta_por_clave')]

    def __str__(self):
        return f'{self.get_tipo_display().lower()} {self.codigo}'

    @classmethod
    def para(cls, proyecto, tipo, clave):
        """La etiqueta de esa clave en el proyecto; la crea la primera vez que se imprime."""
        h = huella(clave)
        for _ in range(5):
            e = cls.objects.filter(proyecto=proyecto, tipo=tipo, huella=h).first()
            if e is not None:
                return e
            try:
                with transaction.atomic():
                    return cls.objects.create(proyecto=proyecto, tipo=tipo, clave=clave, huella=h,
                                              codigo=codigo_nuevo())
            except IntegrityError:
                continue        # código repetido (de cualquier taller) o la creó otro pedido a la vez
        raise RuntimeError('No se pudo crear el código de la etiqueta')


class FormatoEtiquetas(DatoDeTaller):
    """Cómo imprime etiquetas el taller: se guarda cada vez que imprime. `ajuste_*` corre todo unos mm para
    corregir la impresora; los demás números solo valen para 'a medida'."""
    MEDIDA_HOJA, MEDIDA_ROLLO = 'hoja-medida', 'rollo-medida'
    OPCIONES = [
        ('a4-3x8', 'Hoja A4 · 3 × 8 · 70 × 37 mm'),
        ('a4-3x7', 'Hoja A4 · 3 × 7 · 63,5 × 38,1 mm'),
        ('a4-2x7', 'Hoja A4 · 2 × 7 · 99,1 × 38,1 mm'),
        ('a4-2x4', 'Hoja A4 · 2 × 4 · 99,1 × 67,7 mm'),
        (MEDIDA_HOJA, 'Hoja A4 a medida'),
        ('rollo-100x50', 'Rollo térmico · 100 × 50 mm'),
        ('rollo-62x40', 'Rollo térmico · 62 × 40 mm'),
        (MEDIDA_ROLLO, 'Rollo a medida'),
    ]

    formato = models.CharField('formato', max_length=12, choices=OPCIONES, default='a4-3x8')
    ancho = models.DecimalField('ancho de la etiqueta (mm)', max_digits=5, decimal_places=1, default=70)
    alto = models.DecimalField('alto de la etiqueta (mm)', max_digits=5, decimal_places=1, default=37)
    columnas = models.PositiveSmallIntegerField('columnas', default=3)
    filas = models.PositiveSmallIntegerField('filas', default=8)
    margen_sup = models.DecimalField('margen de arriba (mm)', max_digits=5, decimal_places=1, default=0)
    margen_izq = models.DecimalField('margen de la izquierda (mm)', max_digits=5, decimal_places=1, default=0)
    sep_h = models.DecimalField('separación entre columnas (mm)', max_digits=5, decimal_places=1, default=0)
    sep_v = models.DecimalField('separación entre filas (mm)', max_digits=5, decimal_places=1, default=0)
    ajuste_x = models.DecimalField('correr a la derecha (mm)', max_digits=4, decimal_places=1, default=0)
    ajuste_y = models.DecimalField('correr hacia abajo (mm)', max_digits=4, decimal_places=1, default=0)
    bordes = models.BooleanField('dibujar el borde de cada etiqueta', default=False)
    ESQUEMAS = [('mueble', 'Esquema del mueble'), ('proyecto', 'Proyecto con el mueble marcado'),
                ('ninguno', 'Sin esquema')]
    esquema = models.CharField('dibujo en la etiqueta del mueble', max_length=8, choices=ESQUEMAS, default='mueble')
    actualizado = models.DateTimeField('actualizado', auto_now=True)

    class Meta:
        verbose_name = 'formato de etiquetas'
        verbose_name_plural = 'formatos de etiquetas'
        constraints = [models.UniqueConstraint(fields=['taller'], name='un_formato_por_taller')]

    def __str__(self):
        return self.get_formato_display()

    @property
    def es_hoja(self):
        return self.formato.startswith('a4') or self.formato == self.MEDIDA_HOJA

    def para_pdf(self):
        """El `pdf.Formato` a usar, con el ajuste fino sumado a los márgenes."""
        from dataclasses import replace
        from .pdf import Formato
        if self.formato in FORMATOS:
            f = FORMATOS[self.formato]
        else:
            f = Formato('hoja' if self.es_hoja else 'rollo', float(self.ancho), float(self.alto),
                        self.columnas if self.es_hoja else 1, self.filas if self.es_hoja else 1,
                        float(self.margen_sup), float(self.margen_izq), float(self.sep_h), float(self.sep_v))
        return replace(f, margen_sup=f.margen_sup + float(self.ajuste_y), margen_izq=f.margen_izq + float(self.ajuste_x),
                       bordes=self.bordes, esquema=self.esquema)
