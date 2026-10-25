"""Ficha 23: cada taller pasa a tener sus roles; el rol de texto de cada miembro e invitación pasa a la FK."""
from django.db import migrations

# Los roles con que arranca cada taller (como talleres/permisos.py, BASES, al momento de esta migración): los mismos
# accesos que tenían los cuatro roles fijos. 'dueno' pasa a 'admin' (Administrador).
TODOS = ['visor', 'tareas', 'tareas_gestion', 'proyectos', 'proyectos_gestion', 'proyectos_borrar', 'puesto', 'tablero',
         'produccion_gestion', 'ubicaciones', 'procesos', 'materiales', 'equipo', 'roles', 'marca']
DE_TODOS = ['visor', 'tareas', 'proyectos', 'puesto', 'tablero']
BASES = [
    ('admin', 'Administrador', False, TODOS),
    ('oficina', 'Oficina', False, [c for c in TODOS if c not in ('roles', 'marca', 'proyectos_borrar', 'procesos')]),
    ('armador', 'Armador', True, DE_TODOS),
    ('instalador', 'Instalador', True, DE_TODOS),
]
VIEJO = {'dueno': 'admin', 'oficina': 'oficina', 'armador': 'armador', 'instalador': 'instalador'}


def pasar_a_roles(apps, schema_editor):
    Taller, Rol = apps.get_model('talleres', 'Taller'), apps.get_model('talleres', 'Rol')
    Membresia, Invitacion = apps.get_model('talleres', 'Membresia'), apps.get_model('talleres', 'Invitacion')
    for taller in Taller.objects.order_by('pk'):
        roles = {base: Rol.objects.create(taller=taller, base=base, nombre=nombre, con_pin=con_pin,
                                          permisos=list(permisos), orden=orden)
                 for orden, (base, nombre, con_pin, permisos) in enumerate(BASES)}
        for modelo in (Membresia, Invitacion):
            for viejo, base in VIEJO.items():
                modelo.objects.filter(taller=taller, rol=viejo).update(rol_nuevo=roles[base])


class Migration(migrations.Migration):

    dependencies = [
        ('talleres', '0005_roles_propios'),
    ]

    operations = [
        migrations.RunPython(pasar_a_roles, migrations.RunPython.noop),
    ]
