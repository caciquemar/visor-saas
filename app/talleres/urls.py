"""Direcciones dentro de un taller: app.<dominio>/<taller>/... (ver config/urls.py)."""
from django.urls import include, path

from . import vistas

app_name = 'taller'

urlpatterns = [
    path('', vistas.inicio, name='inicio'),
    path('equipo/', vistas.equipo, name='equipo'),
    path('equipo/invitar/', vistas.invitar, name='invitar'),
    path('equipo/alta/', vistas.alta_con_pin, name='alta_con_pin'),
    path('equipo/<int:id>/', vistas.editar_miembro, name='miembro'),
    path('pin/', vistas.entrar_con_pin, name='pin'),
    path('marca/', vistas.marca, name='marca'),
    path('marca/logo/', vistas.logo, name='logo'),
    path('', include('proyectos.urls')),
]
