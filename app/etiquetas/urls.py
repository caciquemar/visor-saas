"""Direcciones de etiquetas dentro de un taller (se incluyen en talleres/urls.py). Las del QR van sin barra al
final: cuanto más corta la dirección, más grandes los puntos del QR."""
from django.urls import path

from . import vistas

app_name = 'etiquetas'

urlpatterns = [
    path('e/<str:codigo>', vistas.abrir, name='abrir'),
    path('e/<str:codigo>/<int:bulto>', vistas.abrir, name='abrir_bulto'),
    path('visor/api/etiqueta/<str:codigo>', vistas.api, name='api'),
    path('proyectos/<int:id>/etiquetas/', vistas.imprimir, name='imprimir'),
]
