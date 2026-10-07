"""Direcciones de los módulos dentro de un proyecto (se incluyen en proyectos/urls.py, mismo espacio de nombres).
Cada vista lleva `con_modulo`: con el módulo apagado dan 404."""
from django.urls import path

from .zicar import vistas as zicar

urlpatterns = [
    path('proyectos/<int:id>/versiones/<int:numero>/zicar/', zicar.descargar, name='descargar_zicar'),
]
