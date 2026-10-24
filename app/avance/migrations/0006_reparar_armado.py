"""Repara 0004 en las bases donde ya corrió: tomó como Armado la última etapa prendida, y en un taller cuya última
etapa era otra cosa (por ejemplo "Instalacion") la convirtió en el proceso fijo Armado. Si el Armado no se llama como
el armado ("Armado", "Armada", "Ensamble"…), vuelve a ser un proceso del taller por pieza, con sus marcas, y se crea
un Armado nuevo (prendido)."""
import re

from django.db import migrations


def reparar(apps, schema_editor):
    Etapa = apps.get_model('avance', 'Etapa')
    for e in Etapa.objects.filter(tipo='armado'):
        if re.search(r'armad|ensambl', e.nombre, re.I):
            continue
        e.tipo, e.por_mueble = 'pieza', False
        e.save(update_fields=['tipo', 'por_mueble'])
        Etapa.objects.create(taller_id=e.taller_id, nombre='Armado', orden=101, tipo='armado', por_mueble=True)


class Migration(migrations.Migration):

    dependencies = [
        ('avance', '0005_anotaciones'),
    ]

    operations = [
        migrations.RunPython(reparar, migrations.RunPython.noop),
    ]
