"""Link del cliente: /c/<código>/... Sin login; el taller sale del link (talleres/middleware.py)."""
from django.urls import path

from . import visor

app_name = 'cliente'

urlpatterns = [
    path('<str:codigo>/', visor.cliente, name='pagina'),
    path('<str:codigo>/logo', visor.logo_cliente, name='logo'),
    path('<str:codigo>/data/<path:ruta>', visor.dato_cliente, name='dato'),
    path('<str:codigo>/probador/ar', visor.probador_ar, name='probador_ar'),
    path('<str:codigo>/probador/elegir', visor.probador_elegir, name='probador_elegir'),
]
