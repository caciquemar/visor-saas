"""Los tres planes de docs/plan.md (se cambian después en la administración) y una suscripción para cada taller que
ya existía: esos (Nord Good y los pilotos) quedan "sin cobro" con el plan Fábrica, para que nada se corte al
instalar. Martín les pone fecha en la administración cuando corresponda."""
from datetime import date

from django.db import migrations

PLANES = [
    # clave, nombre, USD, proyectos, usuarios, funciones, orden
    ('taller', 'Taller', 19, 10, 3, ['trabajos'], 1),
    ('pro', 'Pro', 39, None, None,
     ['trabajos', 'fotos_de_trabajos', 'avance', 'realidad_aumentada', 'probador', 'logo_en_link'], 2),
    ('fabrica', 'Fábrica', 79, None, None,
     ['trabajos', 'fotos_de_trabajos', 'avance', 'realidad_aumentada', 'probador', 'logo_en_link',
      'colores_en_link'], 3),
]
SIN_COBRO = date(2099, 12, 31)


def crear(apps, schema_editor):
    Plan = apps.get_model('suscripciones', 'Plan')
    Taller = apps.get_model('talleres', 'Taller')
    Suscripcion = apps.get_model('suscripciones', 'Suscripcion')
    for clave, nombre, usd, proyectos, usuarios, funciones, orden in PLANES:
        Plan.objects.get_or_create(clave=clave, defaults=dict(nombre=nombre, precio_usd=usd, max_proyectos=proyectos,
                                                              max_usuarios=usuarios, funciones=funciones, orden=orden))
    fabrica = Plan.objects.get(clave='fabrica')
    hoy = date.today()
    for taller in Taller.objects.all():
        if not Suscripcion.objects.filter(taller=taller).exists():
            Suscripcion.objects.create(taller=taller, plan=fabrica, prueba_hasta=hoy, sin_cobro_hasta=SIN_COBRO,
                                       estado='activa', estado_desde=hoy)


class Migration(migrations.Migration):

    dependencies = [
        ('suscripciones', '0001_initial'),
        ('talleres', '0007_rol_es_fk'),
    ]

    operations = [
        migrations.RunPython(crear, migrations.RunPython.noop),
    ]
