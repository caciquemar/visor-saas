"""/pagos/...: lo que llama la pasarela, sin sesión. El aviso no aprueba nada por sí solo (vistas.aviso)."""
from django.urls import path

from . import vistas

app_name = 'pagos'

urlpatterns = [
    path('aviso/<slug:slug>/<str:codigo>/', vistas.aviso, name='aviso'),
    path('simulada/<slug:slug>/<str:codigo>/', vistas.simulada, name='simulada'),   # solo con PASARELA=simulada
]
