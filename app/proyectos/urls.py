"""Direcciones de proyectos y materiales dentro de un taller (se incluyen en talleres/urls.py)."""
from django.urls import path

from . import vistas

app_name = 'proyectos'

urlpatterns = [
    path('proyectos/', vistas.lista, name='lista'),
    path('proyectos/nuevo/', vistas.nuevo, name='nuevo'),
    path('proyectos/<int:id>/', vistas.ver, name='ver'),
    path('proyectos/<int:id>/versiones/nueva/', vistas.nueva_version, name='nueva_version'),
    path('proyectos/<int:id>/versiones/<int:numero>/usar/', vistas.usar_version, name='usar_version'),
    path('proyectos/<int:id>/versiones/<int:numero>/reconvertir/', vistas.reconvertir, name='reconvertir'),
    path('proyectos/<int:id>/versiones/<int:numero>/originales/<int:original_id>/', vistas.original,
         name='original'),
    path('materiales/', vistas.materiales, name='materiales'),
    path('materiales/<int:id>/', vistas.material, name='material'),
    path('materiales/<int:id>/imagen/', vistas.imagen_material, name='imagen_material'),
]
