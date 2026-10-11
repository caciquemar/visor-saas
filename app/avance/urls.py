"""Direcciones de la ficha 13 dentro de un taller (se incluyen en talleres/urls.py)."""
from django.urls import path

from . import api, vistas

app_name = 'avance'

urlpatterns = [
    path('puesto/', vistas.puesto, name='puesto'),
    path('puesto/api/marcar', api.marcar, name='marcar'),
    path('puesto/api/deshacer', api.deshacer, name='deshacer'),
    path('puesto/api/mueble', api.mueble, name='mueble'),
    path('puesto/api/terminar', api.terminar, name='terminar'),
    path('puesto/api/reabrir', api.reabrir, name='reabrir'),
    path('puesto/api/cargas/<int:id>', api.carga, name='api_carga'),
    path('puesto/api/cargas/<int:id>/bulto', api.bulto, name='bulto'),
    path('puesto/api/cargas/<int:id>/deshacer', api.deshacer_bulto, name='deshacer_bulto'),
    path('visor/api/avance', api.avance_visor, name='avance_visor'),
    path('proyectos/<int:id>/cargas/nueva/', vistas.nueva_carga, name='nueva_carga'),
    path('cargas/<int:id>/', vistas.carga, name='carga'),
    path('etapas/', vistas.etapas, name='etapas'),
]
