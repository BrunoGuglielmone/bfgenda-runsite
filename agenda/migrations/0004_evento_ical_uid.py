from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agenda", "0003_preferenciasusuario"),
    ]

    operations = [
        migrations.AddField(
            model_name="evento",
            name="ical_uid",
            field=models.CharField(
                blank=True,
                editable=False,
                max_length=255,
                null=True,
                verbose_name="identificador iCalendar",
            ),
        ),
        migrations.AddConstraint(
            model_name="evento",
            constraint=models.UniqueConstraint(
                condition=models.Q(ical_uid__isnull=False),
                fields=("usuario", "ical_uid"),
                name="evento_ical_uid_unico_por_usuario",
            ),
        ),
    ]
