import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('talleres', '0006_pasar_a_roles'),
    ]

    operations = [
        migrations.RemoveField(model_name='membresia', name='rol'),
        migrations.RemoveField(model_name='invitacion', name='rol'),
        migrations.RenameField(model_name='membresia', old_name='rol_nuevo', new_name='rol'),
        migrations.RenameField(model_name='invitacion', old_name='rol_nuevo', new_name='rol'),
        migrations.AlterField(model_name='membresia', name='rol', field=models.ForeignKey(null=False, on_delete=django.db.models.deletion.PROTECT, related_name='membresias', to='talleres.rol', verbose_name='rol')),
        migrations.AlterField(model_name='invitacion', name='rol', field=models.ForeignKey(null=False, on_delete=django.db.models.deletion.PROTECT, related_name='invitaciones', to='talleres.rol', verbose_name='rol')),
        migrations.AddConstraint(
            model_name='rol',
            constraint=models.UniqueConstraint(condition=models.Q(('base', ''), _negated=True), fields=('taller', 'base'), name='un_rol_inicial'),
        ),
        migrations.AddConstraint(
            model_name='rol',
            constraint=models.UniqueConstraint(fields=('taller', 'nombre'), name='un_nombre_de_rol_por_taller'),
        ),
    ]
