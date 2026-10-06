"""Las versiones convertidas antes de separar tableros y cantos guardaban las texturas faltantes como una lista de
nombres; ahora son [{nombre, tipo}]. Los viejos quedan como tablero (en ese momento no se distinguía): al volver a
convertir se corrigen solos."""
from django.db import migrations


def con_tipo(apps, schema_editor):
    Version = apps.get_model('proyectos', 'Version')
    for v in Version._default_manager.exclude(faltan_texturas=[]):
        if any(isinstance(f, str) for f in v.faltan_texturas):
            v.faltan_texturas = [{'nombre': f, 'tipo': 'tablero'} if isinstance(f, str) else f
                                 for f in v.faltan_texturas]
            v.save(update_fields=['faltan_texturas'])


class Migration(migrations.Migration):

    dependencies = [
        ('proyectos', '0002_material_por_tipo'),
    ]

    operations = [
        migrations.RunPython(con_tipo, migrations.RunPython.noop),
    ]
