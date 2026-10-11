from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operaciones", "0006_evidencia_archivo_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="rutadestino",
            name="hora_inicio_descarga",
            field=models.TimeField(blank=True, null=True, verbose_name="inicio de descarga"),
        ),
        migrations.AddField(
            model_name="rutadestino",
            name="hora_fin_descarga",
            field=models.TimeField(blank=True, null=True, verbose_name="fin de descarga"),
        ),
    ]
