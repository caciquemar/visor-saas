"""Direcciones de las pruebas: las de la app más /<taller>/notas/..."""
from django.urls import include, path

from config.urls import urlpatterns as de_la_app

from . import vistas

notas = ([
    path('', vistas.lista, name='lista'),
    path('nueva/', vistas.nueva, name='nueva'),
    path('<int:id>/', vistas.ver, name='ver'),
    path('<int:id>/editar/', vistas.editar, name='editar'),
    path('<int:id>/borrar/', vistas.borrar, name='borrar'),
    path('<int:id>/archivo/', vistas.archivo_de_nota, name='archivo'),
    path('archivos/<path:ruta>', vistas.archivo_por_ruta, name='archivo_por_ruta'),
], 'notas')

urlpatterns = [path('<slug:taller>/notas/', include(notas)), *de_la_app]
