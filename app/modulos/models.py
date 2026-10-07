"""Módulos: funciones extra que se prenden por taller (regla 3 de CLAUDE.md). `Modulo` es el catálogo del servicio
(uno por módulo que existe en el código, ver modulos/registro.py); `TallerModulo` dice si un taller lo tiene prendido
y con qué configuración. Se manejan solo desde la administración."""
from django.db import models

from talleres.separacion import DatoDeTaller


class Modulo(models.Model):
    clave = models.SlugField('clave', max_length=40, unique=True,
                             help_text='La que usa el código (por ejemplo "zicar"). No se cambia.')
    nombre = models.CharField('nombre', max_length=100)
    descripcion = models.TextField('descripción', blank=True)

    class Meta:
        verbose_name = 'módulo'
        verbose_name_plural = 'módulos'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class TallerModulo(DatoDeTaller):
    modulo = models.ForeignKey(Modulo, on_delete=models.PROTECT, related_name='+', verbose_name='módulo')
    prendido = models.BooleanField('prendido', default=True)
    configuracion = models.JSONField('configuración', default=dict, blank=True)

    class Meta:
        verbose_name = 'módulo del taller'
        verbose_name_plural = 'módulos del taller'
        ordering = ['modulo__nombre']
        constraints = [models.UniqueConstraint(fields=['taller', 'modulo'], name='un_modulo_por_taller')]

    def __str__(self):
        return f'{self.modulo} ({"prendido" if self.prendido else "apagado"})'
