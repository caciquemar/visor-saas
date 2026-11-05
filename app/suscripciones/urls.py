"""Mi suscripción, dentro del taller: /<taller>/suscripcion/... (se incluye en talleres/urls.py)."""
from django.urls import path

from . import vistas

app_name = 'suscripcion'

urlpatterns = [
    path('', vistas.pantalla, name='pantalla'),
    path('pagar/', vistas.pagar, name='pagar'),
    path('volver/<str:codigo>/', vistas.volver, name='volver'),
]
