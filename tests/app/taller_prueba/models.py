"""Modelo de prueba con datos de taller: un texto, una FK a otra nota del mismo taller y un archivo.
Hace de 'proyecto' o 'trabajo' hasta que existan (fichas 03 y 05)."""
from django.db import models

from talleres.archivos import ruta_de_taller
from talleres.separacion import DatoDeTaller


class Nota(DatoDeTaller):
    texto = models.CharField(max_length=200)
    padre = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='respuestas')
    archivo = models.FileField(upload_to=ruta_de_taller, blank=True)

    def __str__(self):
        return self.texto
