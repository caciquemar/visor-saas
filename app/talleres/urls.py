"""Direcciones dentro de un taller: app.<dominio>/<taller>/... (ver config/urls.py)."""
from django.urls import include, path, re_path

from . import cuenta, vistas

app_name = 'taller'

urlpatterns = [
    path('', vistas.inicio, name='inicio'),
    re_path(r'^(?P<seccion>armado|produccion|configuracion)/$', vistas.seccion, name='seccion'),
    path('cuenta/', cuenta.mi_cuenta, name='cuenta'),
    path('equipo/', vistas.equipo, name='equipo'),
    path('equipo/agregar/', vistas.agregar_persona, name='agregar_persona'),
    path('equipo/invitacion/<int:id>/reenviar/', vistas.reenviar_invitacion, name='reenviar_invitacion'),
    path('equipo/invitacion/<int:id>/anular/', vistas.anular_invitacion, name='anular_invitacion'),
    path('equipo/roles/nuevo/', vistas.rol, name='rol_nuevo'),
    path('equipo/roles/<int:id>/', vistas.rol, name='rol'),
    path('equipo/<int:id>/', vistas.editar_miembro, name='miembro'),
    path('pin/', vistas.entrar_con_pin, name='pin'),
    path('marca/', vistas.marca, name='marca'),
    path('marca/logo/', vistas.logo, name='logo'),
    path('', include('proyectos.urls')),
    path('', include('etiquetas.urls')),
    path('', include('avance.urls')),
    path('visor/api/', include('trabajos.urls')),
    path('trabajos/', include('trabajos.urls_pantalla')),
]
