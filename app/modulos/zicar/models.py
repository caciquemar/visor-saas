from django.db import models

from proyectos.models import Version
from talleres.separacion import DatoDeTaller


class ResultadoZicar(DatoDeTaller):
    """Los DXF para la Zicar de una versión, generados con pb2zicar a partir de la carpeta del postprocesador."""
    Estado = Version.Estado

    version = models.OneToOneField(Version, on_delete=models.CASCADE, related_name='zicar')
    estado = models.CharField('estado', max_length=12, choices=Estado.choices, default=Estado.EN_COLA)
    mensaje = models.TextField('mensaje de error', blank=True)
    avisos = models.JSONField('para revisar a mano', default=list, blank=True)
    piezas = models.PositiveIntegerField('piezas convertidas', default=0)
    archivo = models.CharField('ZIP', max_length=400, blank=True)
    nombre = models.CharField('nombre del ZIP', max_length=200, blank=True)
    creado = models.DateTimeField('creado', auto_now_add=True)
    empezado = models.DateTimeField('empezado', null=True, blank=True)
    terminado = models.DateTimeField('terminado', null=True, blank=True)

    class Meta:
        verbose_name = 'resultado Zicar'
        verbose_name_plural = 'resultados Zicar'

    def __str__(self):
        return f'Zicar de {self.version}'

    @property
    def en_proceso(self):
        return self.estado in (self.Estado.EN_COLA, self.Estado.CONVIRTIENDO)
