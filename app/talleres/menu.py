"""Cómo se encuentran las pantallas del taller: el Inicio con un botón grande por sección (talleres/inicio.html), la
pantalla de cada sección (talleres/seccion.html), el menú ☰ de todas las páginas (templates/menu.html) y el del
visor (proyectos/visor.py, menu_de). Todo sale de SECCIONES, así se encuentra todo en el mismo lugar."""
from django.urls import reverse


# (clave, nombre, para qué sirve, pantallas). Una sección con una sola pantalla (Visor, Proyectos) va directo a ella;
# las demás tienen su pantalla en /<taller>/<clave>/. Tareas no está en el menú: se abre desde la lista de arriba del
# visor y es un modo de Mi puesto.
# Cada pantalla: (nombre, ruta, para qué sirve, permisos que la abren (alguno), ícono de talleres/iconos.py). La sección usa el
# ícono de su clave.
SECCIONES = [
    # el visor va directo (pedido de Martín, 2026-11-13): las tareas se abren desde su lista de arriba
    ('visor', 'Visor', 'El mueble en 3D, pieza por pieza, y lo que falta hacer o instalar.', [
        ('Visor', 'taller:proyectos:visor', '', ('visor',), 'visor'),
    ]),
    ('proyectos', 'Proyectos', 'Subí los proyectos de Polyboard, mandale el link al cliente e imprimí etiquetas.', [
        ('Proyectos', 'taller:proyectos:lista', '', ('proyectos',), 'proyectos'),
    ]),
    ('produccion', 'Producción', 'Mi puesto para escanear, el tablero de control y los procesos del taller.', [
        ('Mi puesto', 'taller:avance:puesto',
         'Escaneá las etiquetas para marcar cada etapa, dejar las piezas en su lugar, terminar un mueble o cargar.',
         ('puesto',), 'puesto'),
        ('Tablero de control', 'taller:avance:tablero', 'El avance de cada proyecto, por etapa y en general.', ('tablero',),
         'tablero'),
        ('Procesos', 'taller:avance:procesos', 'Las etapas de las piezas y las ubicaciones del taller.',
         ('procesos', 'ubicaciones'),
         'procesos'),
    ]),
    ('configuracion', 'Configuración', 'Materiales, equipo y marca del taller.', [
        ('Materiales', 'taller:proyectos:materiales', 'Texturas de tableros y cantos, y el color sin canto.', ('materiales',),
         'materiales'),
        ('Equipo', 'taller:equipo', 'Las personas del taller y sus roles.', ('equipo', 'roles'), 'equipo'),
        ('Marca', 'taller:marca', 'Tu logo y tu color en el link del cliente.', ('marca',), 'marca'),
        ('Suscripción', 'taller:suscripcion:pantalla', 'Tu plan, hasta cuándo está pago y pagar.', ('suscripcion',),
         'suscripcion'),
    ]),
]

# Pantallas que dependen del plan (ficha 08): función de talleres/limites.py que necesitan. Suscripción aparece solo
# con el cobro activo (administración → Configuración del cobro).
FUNCION_DE_PANTALLA = {'taller:avance:puesto': 'avance', 'taller:avance:tablero': 'avance',
                       'taller:avance:procesos': 'avance'}
SOLO_CON_COBRO = {'taller:suscripcion:pantalla'}


def segun_plan(taller, ruta):
    from .limites import activas, permite
    if ruta in SOLO_CON_COBRO:
        return activas()
    funcion = FUNCION_DE_PANTALLA.get(ruta)
    return funcion is None or permite(taller, funcion)


def secciones(request):
    """Las secciones con las pantallas que el rol de la sesión puede abrir (sin las que quedan vacías). Cada una:
    clave, nombre, descripcion, url (la de su pantalla, o la única que tiene) y pantallas."""
    taller, membresia = getattr(request, 'taller', None), getattr(request, 'membresia', None)
    if taller is None or membresia is None:
        return []
    url = lambda ruta, **kw: reverse(ruta, kwargs={'taller': taller.slug, **kw})
    lista = []
    for clave, nombre, descripcion, todas in SECCIONES:
        pantallas = [{'nombre': n, 'url': url(ruta), 'descripcion': d, 'icono': i} for n, ruta, d, roles, i in todas
                     if any(membresia.puede(p) for p in roles) and segun_plan(taller, ruta)]
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
    menu = [{'nombre': 'Inicio', 'url': reverse('taller:inicio', kwargs={'taller': request.taller.slug}),
             'icono': 'inicio'}]
    for s in lista:
        menu.append({'nombre': s['nombre'], 'url': s['url'], 'seccion': True, 'icono': s['clave']})
        if not s['directa']:
            menu += [{'nombre': p['nombre'], 'url': p['url'], 'sub': True, 'icono': p['icono']} for p in s['pantallas']]
    return menu


def menu(request):
    """Procesador de contexto: `menu` para templates/menu.html, con la pantalla actual marcada (la de dirección
    más larga que empieza igual; Inicio solo si es exactamente esa). Si una pantalla
    está en dos secciones, se marca en las dos."""
    lista = pantallas(request)
    if not lista:
        return {'menu': []}
    inicio = lista[0]['url']
    candidatas = [x for x in lista[1:] if request.path.startswith(x['url'])]
    larga = max((len(x['url']) for x in candidatas), default=0)
    return {'menu': [dict(x, actual=(len(x['url']) == larga and x in candidatas) if candidatas
                          else (x is lista[0] and request.path == inicio)) for x in lista]}
