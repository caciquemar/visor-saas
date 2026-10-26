"""Direcciones de proyectos y materiales dentro de un taller (se incluyen en talleres/urls.py)."""
from django.urls import include, path

from . import visor, vistas

app_name = 'proyectos'

urlpatterns = [
    path('proyectos/', vistas.lista, name='lista'),
    path('proyectos/nuevo/', vistas.nuevo, name='nuevo'),
    path('proyectos/<int:id>/', vistas.ver, name='ver'),
    path('proyectos/<int:id>/datos/', vistas.datos, name='datos'),
    path('proyectos/<int:id>/produccion/', vistas.produccion, name='produccion'),
    path('proyectos/<int:id>/archivar/', vistas.archivar, name='archivar'),
    path('proyectos/<int:id>/desarchivar/', vistas.desarchivar, name='desarchivar'),
    path('proyectos/<int:id>/borrar/', vistas.borrar, name='borrar'),
    path('proyectos/<int:id>/versiones/nueva/', vistas.nueva_version, name='nueva_version'),
    path('proyectos/<int:id>/versiones/<int:numero>/usar/', vistas.usar_version, name='usar_version'),
    path('proyectos/<int:id>/versiones/<int:numero>/reconvertir/', vistas.reconvertir, name='reconvertir'),
    path('proyectos/<int:id>/versiones/<int:numero>/borrar/', vistas.borrar_version, name='borrar_version'),
    path('proyectos/<int:id>/versiones/<int:numero>/originales/<int:original_id>/', vistas.original,
         name='original'),
    path('proyectos/<int:id>/links/nuevo/', vistas.nuevo_link, name='nuevo_link'),
    path('proyectos/<int:id>/links/<int:link_id>/anular/', vistas.anular_link, name='anular_link'),
    path('proyectos/<int:id>/colores/nuevo/', vistas.grupo_color, name='grupo_color_nuevo'),
    path('proyectos/<int:id>/colores/<int:grupo_id>/', vistas.grupo_color, name='grupo_color'),
    path('materiales/', vistas.materiales, name='materiales'),
    path('materiales/sin-canto/', vistas.sin_canto, name='sin_canto'),
    path('materiales/buscar-lisos/', vistas.buscar_lisos, name='buscar_lisos'),
    path('materiales/importar/', vistas.importar_biblioteca, name='importar_biblioteca'),
    path('materiales/importar/textura/', vistas.importar_textura, name='importar_textura'),
    path('materiales/nuevo-<str:tipo>/', vistas.nuevo_material, name='nuevo_material'),
    path('materiales/<int:id>/', vistas.material, name='material'),
    path('materiales/<int:id>/borrar/', vistas.borrar_material, name='borrar_material'),
    path('materiales/<int:id>/imagen/', vistas.imagen_material, name='imagen_material'),
    # el visor: sus rutas relativas (data/…, manifest.webmanifest) quedan debajo de visor/
    path('visor/', visor.visor, name='visor'),
    path('visor/manifest.webmanifest', visor.manifest, name='visor_manifest'),
    path('visor/data/index.json', visor.indice, name='visor_indice'),
    path('visor/data/materiales.json', visor.miembro_sin_colores, name='visor_materiales'),
    path('visor/data/<int:id>/<path:ruta>', visor.dato, name='visor_dato'),
    path('', include('modulos.urls')),        # módulos por taller: 404 si no están prendidos
]
