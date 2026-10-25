"""Quién puede abrir cada vista dentro de /<taller>/: el middleware ya garantizó que la membresía es de este taller;
acá solo se miran los permisos de su rol (ficha 23, talleres/permisos.py)."""
from functools import wraps

from django.core.exceptions import PermissionDenied
from django.http import Http404

from .permisos import CLAVES


def con_permiso(*permisos):
    """La vista abre si el rol tiene alguno de esos permisos."""
    desconocidos = set(permisos) - set(CLAVES)
    if desconocidos:
        raise ValueError(f'Permisos que no existen: {desconocidos}')

    def decorador(vista):
        @wraps(vista)
        def envuelta(request, *args, **kwargs):
            membresia = getattr(request, 'membresia', None)
            if membresia is None:
                raise Http404()
            if not any(membresia.puede(p) for p in permisos):
                raise PermissionDenied('Tu rol no tiene acceso a esta pantalla.')
            return vista(request, *args, **kwargs)
        return envuelta
    return decorador


def miembro(vista):
    """Cualquier miembro del taller (también con PIN)."""
    @wraps(vista)
    def envuelta(request, *args, **kwargs):
        if getattr(request, 'membresia', None) is None:
            raise Http404()
        return vista(request, *args, **kwargs)
    return envuelta


def puede(request, permiso):
    membresia = getattr(request, 'membresia', None)
    return membresia is not None and membresia.puede(permiso)
