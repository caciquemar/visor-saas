"""Pantalla "Trabajos" del taller, en /<taller>/trabajos/ (se incluye en talleres/urls.py). Ver trabajos/vistas.py."""
from django.urls import path

from . import vistas

app_name = 'trabajos'

urlpatterns = [
    path('', vistas.lista, name='lista'),
    path('<int:id>/avanzar/', vistas.avanzar, name='avanzar'),
]
