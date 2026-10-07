from django.db import migrations


def crear(apps, schema_editor):
    Modulo = apps.get_model('modulos', 'Modulo')
    Modulo.objects.get_or_create(clave='zicar', defaults=dict(
        nombre='Zicar',
        descripcion='DXF para la CNC Zicar a partir de la carpeta del postprocesador de Polyboard. Solo Nord Good.'))


class Migration(migrations.Migration):

    dependencies = [
        ('modulos', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(crear, migrations.RunPython.noop),
    ]
