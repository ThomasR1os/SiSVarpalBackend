from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operaciones", "0007_rutadestino_horas_descarga"),
    ]

    operations = [
        migrations.AlterField(
            model_name="destino",
            name="estado",
            field=models.CharField(
                choices=[
                    ("NO_INICIADO", "No iniciado"),
                    ("EN_PROCESO", "En proceso"),
                    ("PENDIENTE", "Pendiente"),
                    ("EXITOSO", "Exitoso"),
                    ("FALLIDO", "Fallido"),
                ],
                default="NO_INICIADO",
                max_length=20,
            ),
        ),
    ]
