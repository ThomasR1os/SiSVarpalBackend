from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operaciones", "0004_alter_destino_latitud_alter_destino_longitud_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="ruta",
            name="distancia_cliente_metros",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="ruta",
            name="duracion_cliente_segundos",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
