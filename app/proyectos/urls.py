"""Direcciones de proyectos y materiales dentro de un taller (se incluyen en talleres/urls.py)."""
from django.urls import include, path

from . import visor, vistas

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
    path('proyectos/<int:id>/links/nuevo/', vistas.nuevo_link, name='nuevo_link'),
    path('proyectos/<int:id>/links/<int:link_id>/anular/', vistas.anular_link, name='anular_link'),
    path('materiales/', vistas.materiales, name='materiales'),
    path('materiales/sin-canto/', vistas.sin_canto, name='sin_canto'),
    path('materiales/<int:id>/', vistas.material, name='material'),
    path('materiales/<int:id>/imagen/', vistas.imagen_material, name='imagen_material'),
    # el visor: sus rutas relativas (data/…, manifest.webmanifest) quedan debajo de visor/
    path('visor/', visor.visor, name='visor'),
    path('visor/manifest.webmanifest', visor.manifest, name='visor_manifest'),
    path('visor/data/index.json', visor.indice, name='visor_indice'),
    path('visor/data/materiales.json', visor.miembro_sin_colores, name='visor_materiales'),
    path('visor/data/<int:id>/<path:ruta>', visor.dato, name='visor_dato'),
    path('', include('modulos.urls')),        # módulos por taller: 404 si no están prendidos
]
