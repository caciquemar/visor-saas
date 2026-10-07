"""Única puerta a los módulos. El resto de la app no pregunta por un módulo en particular: pide los ganchos de los
módulos prendidos en el taller actual y los llama. Si un módulo no está prendido, no aparece nada y sus direcciones
dan 404 (`con_modulo`), igual que una dirección que no existe.

Cada módulo es una subclase de `Modulo` registrada con `@registrar` (se importa en el `ready()` de su app). Los
ganchos son opcionales:

- `campos_de_subida(form)`            suma campos al formulario de subida (proyecto nuevo o versión nueva).
- `html_de_subida(form)`              HTML de esos campos en la pantalla de subida.
- `al_guardar_version(version, datos)` guarda lo suyo de la subida (`datos` = cleaned_data del formulario).
- `al_encolar(version)`               paso extra de la conversión (versión nueva o "Volver a convertir").
- `en_proceso(version)`               True si su paso todavía no terminó (la página se actualiza sola).
- `html_de_version(request, proyecto, version)`  HTML en la caja de la versión (botones, estado).
- `oculta_original(original)`         True si el archivo subido es suyo (no se lista si el módulo se apaga).
"""
from functools import wraps

from django.http import Http404

from talleres.separacion import taller_actual

_MODULOS = {}


class Modulo:
    clave = ''

    def disponible(self):
        """False si falta algo en el servidor (por ejemplo, un paquete): el módulo no se activa aunque esté prendido."""
        return True

    def campos_de_subida(self, form):
        pass

    def html_de_subida(self, form):
        return ''

    def al_guardar_version(self, version, datos):
        pass

    def al_encolar(self, version):
        pass

    def en_proceso(self, version):
        return False

    def html_de_version(self, request, proyecto, version):
        return ''

    def oculta_original(self, original):
        return False


def registrar(clase):
    _MODULOS[clase.clave] = clase()
    return clase


def registrados():
    return dict(_MODULOS)


def claves_prendidas():
    """Claves de los módulos prendidos en el taller actual (sin taller: ninguno)."""
    if taller_actual.get() is None:
        return set()
    from .models import TallerModulo
    return set(TallerModulo.objects.filter(prendido=True).values_list('modulo__clave', flat=True))


def activos():
    """Los módulos prendidos en el taller actual y disponibles en el servidor."""
    prendidas = claves_prendidas()
    return [m for clave, m in _MODULOS.items() if clave in prendidas and m.disponible()]


def prendido(clave):
    return any(m.clave == clave for m in activos())


def oculto(original, modulos=None):
    """True si el archivo subido es de un módulo que hoy no está activo en el taller (`modulos`: los activos, si ya
    se pidieron)."""
    activas = {m.clave for m in (activos() if modulos is None else modulos)}
    return any(m.oculta_original(original) for clave, m in _MODULOS.items() if clave not in activas)


def con_modulo(clave):
    """Para vistas de un módulo: 404 si no está prendido en el taller del pedido. Va antes que `con_rol`, así la
    respuesta es la misma que la de una dirección que no existe."""
    def decorador(vista):
        @wraps(vista)
        def envuelta(request, *args, **kwargs):
            if getattr(request, 'taller', None) is None or not prendido(clave):
                raise Http404()
            return vista(request, *args, **kwargs)
        return envuelta
    return decorador
