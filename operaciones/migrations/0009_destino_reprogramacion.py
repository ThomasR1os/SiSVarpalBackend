from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operaciones", "0008_destino_estado_pendiente"),
    ]

    operations = [
        migrations.AddField(
            model_name="destino",
            name="reprogramacion_pendiente",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="destino",
            name="fecha_anterior",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="destino",
            name="motivo_reprogramacion",
            field=models.TextField(blank=True),
        ),
    ]
