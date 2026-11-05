from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agenda", "0010_monitor_automatizacion"),
    ]

    operations = [
        migrations.AddField(
            model_name="preferenciasusuario",
            name="tema_interfaz",
            field=models.CharField(
                choices=[
                    ("sistema", "Automático (según el sistema)"),
                    ("claro", "Claro"),
                    ("oscuro", "Oscuro"),
                ],
                default="sistema",
                max_length=10,
                verbose_name="tema de la interfaz",
            ),
        ),
    ]
