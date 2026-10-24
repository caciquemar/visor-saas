"""Cómo se encuentran las pantallas del taller: el Inicio con un botón grande por sección (talleres/inicio.html), la
pantalla de cada sección (talleres/seccion.html), el menú ☰ de todas las páginas (templates/menu.html) y el del
visor (proyectos/visor.py, menu_de). Todo sale de SECCIONES, así se encuentra todo en el mismo lugar."""
from django.urls import reverse

from .roles import Rol

TODOS = tuple(Rol.values)
GESTION = (Rol.DUENO, Rol.OFICINA)
DUENO = (Rol.DUENO,)

# (clave, nombre, para qué sirve, pantallas). Una sección con una sola pantalla (Proyectos) va directo a ella; las
# demás tienen su pantalla en /<taller>/<clave>/. Trabajos está en Armado y en Producción a propósito (Martín).
# Cada pantalla: (nombre, ruta, para qué sirve, roles que la ven).
SECCIONES = [
    ('armado', 'Armado', 'El mueble en 3D, pieza por pieza, y lo que falta hacer o instalar.', [
        ('Visor', 'taller:proyectos:visor', 'Escaneá una pieza o tocala en el dibujo para ver dónde va.', TODOS),
        ('Trabajos', 'taller:trabajos:lista', 'Lo que falta hacer o instalar en todos los proyectos.', TODOS),
    ]),
    ('proyectos', 'Proyectos', 'Subí los proyectos de Polyboard, mandale el link al cliente e imprimí etiquetas.', [
        ('Proyectos', 'taller:proyectos:lista', '', TODOS),
    ]),
    ('produccion', 'Producción', 'Avance por etapas, fin de fabricación, cargas y trabajos pendientes.', [
        ('Puesto', 'taller:avance:puesto',
         'Escaneá las etiquetas para marcar cada etapa, terminar un mueble o cargar el camión.', TODOS),
        ('Trabajos', 'taller:trabajos:lista', 'Lo que falta hacer o instalar en todos los proyectos.', TODOS),
    ]),
    ('configuracion', 'Configuración', 'Materiales, equipo, marca y etapas del taller.', [
        ('Materiales', 'taller:proyectos:materiales', 'Texturas de tableros y cantos, y el color sin canto.', GESTION),
        ('Equipo', 'taller:equipo', 'Quién entra al taller, con qué rol, invitaciones y PIN.', GESTION),
        ('Marca', 'taller:marca', 'Tu logo y tu color en el link del cliente.', DUENO),
        ('Etapas', 'taller:avance:etapas', 'Las etapas de fabricación que se marcan en el puesto.', DUENO),
    ]),
]


def secciones(request):
    """Las secciones con las pantallas que el rol de la sesión puede abrir (sin las que quedan vacías). Cada una:
    clave, nombre, descripcion, url (la de su pantalla, o la única que tiene) y pantallas."""
    taller, membresia = getattr(request, 'taller', None), getattr(request, 'membresia', None)
    if taller is None or membresia is None:
        return []
    url = lambda ruta, **kw: reverse(ruta, kwargs={'taller': taller.slug, **kw})
    lista = []
    for clave, nombre, descripcion, todas in SECCIONES:
        pantallas = [{'nombre': n, 'url': url(ruta), 'descripcion': d} for n, ruta, d, roles in todas
                     if membresia.rol in roles]
        if not pantallas:
            continue
        directa = len(todas) == 1
        lista.append({'clave': clave, 'nombre': nombre, 'descripcion': descripcion, 'pantallas': pantallas,
                      'directa': directa,
                      'url': pantallas[0]['url'] if directa else url('taller:seccion', seccion=clave)})
    return lista


def pantallas(request):
    """El menú ☰ en orden: Inicio, y cada sección con sus pantallas debajo (`sub`). Una sección directa es una
    sola línea."""
    lista = secciones(request)
    if not lista:
        return []
    menu = [{'nombre': 'Inicio', 'url': reverse('taller:inicio', kwargs={'taller': request.taller.slug})}]
    for s in lista:
        menu.append({'nombre': s['nombre'], 'url': s['url'], 'seccion': True})
        if not s['directa']:
            menu += [{'nombre': p['nombre'], 'url': p['url'], 'sub': True} for p in s['pantallas']]
    return menu


def menu(request):
    """Procesador de contexto: `menu` para templates/menu.html, con la pantalla actual marcada (la de dirección
    más larga que empieza igual; Inicio solo si es exactamente esa). Trabajos, que está en dos secciones, se marca
    en las dos."""
    lista = pantallas(request)
    if not lista:
        return {'menu': []}
    inicio = lista[0]['url']
    candidatas = [x for x in lista[1:] if request.path.startswith(x['url'])]
    larga = max((len(x['url']) for x in candidatas), default=0)
    return {'menu': [dict(x, actual=(len(x['url']) == larga and x in candidatas) if candidatas
                          else (x is lista[0] and request.path == inicio)) for x in lista]}
