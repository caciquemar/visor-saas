"""El menú ☰ de las pantallas del taller: el mismo en todas las páginas (templates/menu.html) y en el visor
(proyectos/visor.py, menu_de)."""
from django.urls import reverse

from .roles import Rol


def pantallas(request):
    """Las pantallas del servicio que el rol de la sesión puede abrir, en el orden del menú."""
    taller, membresia = getattr(request, 'taller', None), getattr(request, 'membresia', None)
    if taller is None or membresia is None:
        return []
    lista = [('Inicio', 'taller:inicio'), ('Visor', 'taller:proyectos:visor'),
             ('Proyectos', 'taller:proyectos:lista'), ('Trabajos', 'taller:trabajos:lista'),
             ('Puesto', 'taller:avance:puesto')]
    if membresia.rol in (Rol.DUENO, Rol.OFICINA):
        lista += [('Materiales', 'taller:proyectos:materiales'), ('Equipo', 'taller:equipo')]
    if membresia.rol == Rol.DUENO:
        lista += [('Marca', 'taller:marca'), ('Etapas', 'taller:avance:etapas')]
    return [{'nombre': nombre, 'url': reverse(ruta, kwargs={'taller': taller.slug})} for nombre, ruta in lista]


def menu(request):
    """Procesador de contexto: `menu` para templates/menu.html, con la pantalla actual marcada (la de dirección
    más larga que empieza igual; Inicio solo si es exactamente esa)."""
    lista = pantallas(request)
    if not lista:
        return {'menu': []}
    inicio = lista[0]['url']
    candidatas = [x for x in lista[1:] if request.path.startswith(x['url'])]
    actual = max(candidatas, key=lambda x: len(x['url'])) if candidatas else (
        lista[0] if request.path == inicio else None)
    return {'menu': [dict(x, actual=x is actual) for x in lista]}
