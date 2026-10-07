from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operaciones", "0005_ruta_metricas_cliente"),
    ]

    operations = [
        migrations.AlterField(
            model_name="evidencia",
            name="archivo",
            field=models.URLField(max_length=1000),
        ),
    ]
