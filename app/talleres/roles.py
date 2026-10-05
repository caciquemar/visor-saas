from functools import wraps

from django.core.exceptions import PermissionDenied
from django.http import Http404

from .models import Membresia

Rol = Membresia.Rol


def con_rol(*roles):
    """Para vistas dentro de /<taller>/: el middleware ya garantizó que la membresía es de este taller;
    acá solo se mira el rol."""
    def decorador(vista):
        @wraps(vista)
        def envuelta(request, *args, **kwargs):
            membresia = getattr(request, 'membresia', None)
            if membresia is None:
                raise Http404()
            if membresia.rol not in roles:
                raise PermissionDenied('Tu rol no tiene acceso a esta pantalla.')
            return vista(request, *args, **kwargs)
        return envuelta
    return decorador


def miembro(vista):
    """Cualquier miembro del taller (también con PIN)."""
    return con_rol(*Rol.values)(vista)
