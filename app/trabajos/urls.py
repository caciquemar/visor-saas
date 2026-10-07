"""API de trabajos, debajo de /<taller>/visor/api/ (se incluye en talleres/urls.py). Ver trabajos/api.py."""
from django.urls import path

from . import api

app_name = 'trabajos_api'

urlpatterns = [
    path('trabajos', api.lista_o_nuevo, name='lista'),
    path('trabajos/<int:id>', api.trabajo, name='trabajo'),
    path('trabajos/<int:id>/fotos', api.fotos, name='fotos'),
    path('trabajos/<int:id>/fotos/<int:foto_id>', api.foto, name='foto'),
    path('fotos/<int:foto_id>', api.ver_foto, name='ver_foto'),
]
