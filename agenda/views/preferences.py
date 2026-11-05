from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.shortcuts import render
from django.urls import reverse

from agenda.forms import PreferenciasUsuarioForm
from agenda.services.backups import (
    BACKUP_AUTOMATIC,
    BACKUP_MANUAL,
    automatic_backup_limit,
    list_backups,
    sqlite_backups_enabled,
)
from agenda.models import ConfiguracionAutomatizacion
from agenda.services.preferences import get_user_preferences
from agenda.services.retention import COMPLETED_TASK_RETENTION_MONTHS
from agenda.services.task_queries import UNDATED_REMINDER_SESSION_KEY

from .common import FormViewConfig, form_response, get_return_url, saved_response


def _preferences_form_config(*, cancel_url: str) -> FormViewConfig:
    return FormViewConfig(
        eyebrow="Configuración",
        title="Editar preferencias",
        description=(
            "Ajusta cómo se abre el calendario, los valores iniciales de los "
            "eventos y los avisos de tareas sin fecha."
        ),
        icon="⚙",
        submit_label="Guardar preferencias",
        cancel_url=cancel_url,
        hidden_fields=(
            {"name": "return_url", "value": cancel_url},
        ),
    )


@login_required
def configuracion(request):
    """Muestra preferencias, copias disponibles y opciones de exportación."""

    preferences = get_user_preferences(request.user)
    local_backups_enabled = sqlite_backups_enabled()
    backups = list_backups() if local_backups_enabled else []
    automatic_backups = [
        backup for backup in backups if backup.kind == BACKUP_AUTOMATIC
    ]
    manual_backups = [backup for backup in backups if backup.kind == BACKUP_MANUAL]
    context = {
        "preferencias": preferences,
        "meses_retencion_completadas": COMPLETED_TASK_RETENTION_MONTHS,
        "copias": backups,
        "ultima_copia": backups[0] if backups else None,
        "cantidad_copias_automaticas": len(automatic_backups),
        "cantidad_copias_manuales": len(manual_backups),
        "limite_copias_automaticas": automatic_backup_limit(),
        "copias_sqlite_habilitadas": local_backups_enabled,
        "automatizacion": (
            ConfiguracionAutomatizacion.objects
            .filter(activa=True)
            .order_by("id")
            .first()
        ),
        "push_public_key": settings.AGENDE_VAPID_PUBLIC_KEY,
        "push_server_enabled": bool(
            settings.AGENDE_VAPID_PUBLIC_KEY
            and settings.AGENDE_VAPID_PRIVATE_KEY
            and settings.AGENDE_VAPID_SUBJECT
        ),
    }
    return render(request, "agenda/configuracion.html", context)


@login_required
def configuracion_editar(request):
    """Actualiza las preferencias mediante el formulario modal reutilizable."""

    preferences = get_user_preferences(request.user)
    fallback = reverse("agenda:configuracion")
    return_url = get_return_url(request, fallback)
    config = _preferences_form_config(cancel_url=return_url)

    if request.method == "POST":
        form = PreferenciasUsuarioForm(request.POST, instance=preferences)

        if form.is_valid():
            form.save()
            request.session.pop(UNDATED_REMINDER_SESSION_KEY, None)
            return saved_response(
                request,
                message="Las preferencias se guardaron correctamente.",
                redirect_url=return_url,
            )

        return form_response(request, form, config, invalid=True)

    form = PreferenciasUsuarioForm(instance=preferences)
    return form_response(request, form, config)
