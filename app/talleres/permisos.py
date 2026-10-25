"""Qué puede hacer cada rol del taller (ficha 23). Los roles son del taller (talleres.models.Rol): cada uno con su
nombre, sus permisos (claves de PERMISOS) y si entra con usuario y PIN. Cuatro se crean solos con cada taller
(BASES); Administrador tiene todo y no se edita.

Un rol que entra con PIN no puede tener los permisos de SENSIBLES: un PIN de 4 números no alcanza para eso."""

# (clave, nombre, grupo)
PERMISOS = [
    ('visor', 'Visor 3D', 'Armado'),
    ('tareas', 'Tareas', 'Armado'),
    ('tareas_gestion', 'Editar y borrar tareas de otros', 'Armado'),
    ('proyectos', 'Ver proyectos', 'Proyectos'),
    ('proyectos_gestion', 'Subir y modificar proyectos (versiones, datos, estado, archivar, link y probador del '
                          'cliente)', 'Proyectos'),
    ('proyectos_borrar', 'Borrar proyectos', 'Proyectos'),
    ('puesto', 'Mi puesto', 'Producción'),
    ('tablero', 'Tablero de control', 'Producción'),
    ('produccion_gestion', 'Corregir producción (reabrir muebles, deshacer instalaciones, anular cargas)',
     'Producción'),
    ('ubicaciones', 'Ubicaciones', 'Producción'),
    ('procesos', 'Procesos y puntos de control', 'Producción'),
    ('materiales', 'Materiales', 'Configuración'),
    ('equipo', 'Equipo (personas)', 'Configuración'),
    ('roles', 'Roles', 'Configuración'),
    ('marca', 'Marca', 'Configuración'),
]
CLAVES = [p[0] for p in PERMISOS]
NOMBRES = {p[0]: p[1] for p in PERMISOS}
SENSIBLES = {'equipo', 'roles', 'marca', 'proyectos_borrar'}

ADMIN, OFICINA, ARMADOR, INSTALADOR = 'admin', 'oficina', 'armador', 'instalador'
DE_TODOS = ['visor', 'tareas', 'proyectos', 'puesto', 'tablero']
# Los roles que se crean con cada taller: (base, nombre, entra con PIN, permisos). Son los mismos accesos que tenían
# los cuatro roles fijos antes de la ficha 23.
BASES = [
    (ADMIN, 'Administrador', False, CLAVES),
    (OFICINA, 'Oficina', False, [c for c in CLAVES if c not in ('roles', 'marca', 'proyectos_borrar', 'procesos')]),
    (ARMADOR, 'Armador', True, DE_TODOS),
    (INSTALADOR, 'Instalador', True, DE_TODOS),
]


def grupos():
    """[(grupo, [(clave, nombre)])] en el orden de PERMISOS, para las casillas de la ficha del rol."""
    salida = []
    for clave, nombre, grupo in PERMISOS:
        if not salida or salida[-1][0] != grupo:
            salida.append((grupo, []))
        salida[-1][1].append((clave, nombre))
    return salida
