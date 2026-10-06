"""Proyectos de Polyboard subidos por el taller. Cada subida es una Version con sus archivos originales; el conversor
corre en la cola (proyectos/tareas.py) y deja el resultado en la carpeta de la versión (proyectos/archivos.py).
Material es la biblioteca de texturas del taller (lo que en el visor actual es materiales.json)."""
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from conversor.polyboard_a_app import clave as clave_de_material
from talleres.archivos import ruta_de_taller
from talleres.separacion import DatoDeTaller

from .archivos import carpeta_de_version, ruta_original


def codigo_nuevo():
    return secrets.token_urlsafe(9)


class Proyecto(DatoDeTaller):
    nombre = models.CharField('nombre', max_length=150)
    # Código del link del cliente (ficha 04). Se pasa al conversor en cada versión para que el link no cambie.
    codigo_cliente = models.CharField('código del cliente', max_length=32, unique=True, default=codigo_nuevo,
                                      editable=False)
    version_actual = models.ForeignKey('Version', on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='+', verbose_name='versión actual')
    creado = models.DateTimeField('creado', auto_now_add=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+')
    actualizado = models.DateTimeField('actualizado', auto_now=True)

    class Meta:
        verbose_name = 'proyecto'
        verbose_name_plural = 'proyectos'
        ordering = ['-actualizado']

    def __str__(self):
        return self.nombre

    def ultima_version(self):
        return self.versiones.order_by('-numero').first()


class Version(DatoDeTaller):
    class Estado(models.TextChoices):
        EN_COLA = 'en_cola', 'En cola'
        CONVIRTIENDO = 'convirtiendo', 'Convirtiendo'
        LISTO = 'listo', 'Listo'
        ERROR = 'error', 'Error'

    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name='versiones')
    numero = models.PositiveIntegerField('número')
    estado = models.CharField('estado', max_length=12, choices=Estado.choices, default=Estado.EN_COLA)
    mensaje = models.TextField('mensaje de error', blank=True)
    avisos = models.JSONField('avisos', default=list, blank=True)
    resumen = models.JSONField('resumen', default=dict, blank=True)
    faltan_texturas = models.JSONField('materiales sin textura', default=list, blank=True)
    archivo_proyecto = models.CharField('JSON del proyecto', max_length=400, blank=True)
    subida_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+')
    creada = models.DateTimeField('creada', auto_now_add=True)
    empezada = models.DateTimeField('empezada', null=True, blank=True)
    terminada = models.DateTimeField('terminada', null=True, blank=True)

    class Meta:
        verbose_name = 'versión'
        verbose_name_plural = 'versiones'
        ordering = ['-numero']
        constraints = [models.UniqueConstraint(fields=['proyecto', 'numero'], name='un_numero_por_proyecto')]

    def __str__(self):
        return f'{self.proyecto} v{self.numero}'

    def carpeta(self):
        return carpeta_de_version(self)

    @property
    def en_proceso(self):
        return self.estado in (self.Estado.EN_COLA, self.Estado.CONVIRTIENDO)

    def revisar_si_se_corto(self):
        """Si el consumidor de la cola se cayó a mitad de una conversión, la versión quedaría 'convirtiendo' para
        siempre: pasado el límite de tiempo (con margen) se marca como error."""
        limite = timedelta(seconds=settings.CONVERSION_SEGUNDOS + 300)
        if self.estado == self.Estado.CONVIRTIENDO and self.empezada and timezone.now() - self.empezada > limite:
            self.estado = self.Estado.ERROR
            self.mensaje = 'Se cortó la conversión. Probá "Volver a convertir"; si vuelve a pasar, avisanos.'
            self.terminada = timezone.now()
            self.save(update_fields=['estado', 'mensaje', 'terminada'])


class Original(DatoDeTaller):
    class Tipo(models.TextChoices):
        DXF = 'dxf', 'DXF 3D'
        OCP = 'ocp', 'Lista de OptiCut'

    version = models.ForeignKey(Version, on_delete=models.CASCADE, related_name='originales')
    tipo = models.CharField('tipo', max_length=3, choices=Tipo.choices)
    nombre = models.CharField('nombre', max_length=255)       # como lo subió el taller
    archivo = models.FileField('archivo', upload_to=ruta_original, max_length=400)
    tamano = models.PositiveBigIntegerField('tamaño', default=0)

    class Meta:
        verbose_name = 'archivo original'
        verbose_name_plural = 'archivos originales'
        ordering = ['tipo', 'nombre']

    def __str__(self):
        return self.nombre


class Material(DatoDeTaller):
    """Un tablero o un canto. Van separados porque muchos se llaman igual y tienen otra imagen."""
    class Tipo(models.TextChoices):
        TABLERO = 'tablero', 'Tablero'
        CANTO = 'canto', 'Canto'

    tipo = models.CharField('tipo', max_length=7, choices=Tipo.choices, default=Tipo.TABLERO, editable=False)
    nombre = models.CharField('nombre', max_length=200)
    clave = models.CharField(max_length=200, editable=False)       # sin mayúsculas ni acentos, como el conversor
    ruta_polyboard = models.CharField('imagen en Polyboard', max_length=300, blank=True)
    ancho_mm = models.PositiveIntegerField('ancho que cubre la imagen (mm)', null=True, blank=True)
    color = models.CharField('color', max_length=7, blank=True)
    textura = models.ImageField('textura', upload_to=ruta_de_taller, blank=True, max_length=300)
    creado = models.DateTimeField('creado', auto_now_add=True)
    actualizado = models.DateTimeField('actualizado', auto_now=True)

    class Meta:
        verbose_name = 'material'
        verbose_name_plural = 'materiales'
        ordering = ['tipo', 'nombre']
        constraints = [models.UniqueConstraint(fields=['taller', 'tipo', 'clave'], name='un_material_por_tipo_y_nombre')]

    def __str__(self):
        return f'{self.get_tipo_display().lower()} {self.nombre}'

    def save(self, *args, **kwargs):
        self.clave = clave_de_material(self.nombre)
        super().save(*args, **kwargs)
