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
    path('puesto/api/tareas', api.tareas, name='tareas'),
    path('puesto/api/armar', api.armar, name='armar'),
    path('puesto/api/embalar', api.embalar, name='embalar'),
    path('puesto/api/bultos', api.bultos, name='bultos'),
    path('puesto/api/control', api.control, name='control'),
    path('puesto/api/instalacion', api.instalacion, name='instalacion'),
    path('puesto/api/instalar', api.instalar, name='instalar'),
    path('puesto/api/desinstalar', api.desinstalar, name='desinstalar'),
    path('puesto/api/instalaciones/<int:id>/fotos', api.fotos_de_instalacion, name='fotos_de_instalacion'),
    path('puesto/api/fotos-de-instalacion/<int:id>', api.foto_de_instalacion, name='foto_de_instalacion'),
    path('visor/api/entrega', api.entrega_visor, name='entrega_visor'),
    path('visor/api/avance-proceso', api.avance_proceso, name='avance_proceso'),
    path('puesto/api/anotar', api.anotar, name='anotar'),
    path('puesto/api/anotaciones/<int:id>/fotos', api.fotos_de_anotacion, name='fotos_de_anotacion'),
    path('puesto/api/fotos-de-anotacion/<int:id>', api.foto_de_anotacion, name='foto_de_anotacion'),
    path('puesto/api/cargas/<int:id>', api.carga, name='api_carga'),
    path('puesto/api/cargas/<int:id>/bulto', api.bulto, name='bulto'),
    path('puesto/api/cargas/<int:id>/deshacer', api.deshacer_bulto, name='deshacer_bulto'),
    path('visor/api/avance', api.avance_visor, name='avance_visor'),
    path('proyectos/<int:id>/cargas/nueva/', vistas.nueva_carga, name='nueva_carga'),
    path('cargas/<int:id>/', vistas.carga, name='carga'),
    path('proyectos/<int:id>/entrega/', vistas.entrega, name='entrega'),
    path('etapas/', vistas.etapas, name='etapas'),
    path('procesos/', vistas.procesos, name='procesos'),
    path('tablero/', vistas.tablero, name='tablero'),
]
