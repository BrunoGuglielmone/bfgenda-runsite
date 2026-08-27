from django.db.models import Q
from django.utils import timezone

from agenda.models import Tarea
from agenda.utils.dates import shift_months


COMPLETED_TASK_RETENTION_MONTHS = 2
CLEANUP_SESSION_KEY = "agenda_completed_cleanup_date"


def completed_task_cutoff(now=None):
    """Fecha y hora a partir de la cual expira el historial completado."""

    local_now = timezone.localtime(now or timezone.now())
    return shift_months(local_now, -COMPLETED_TASK_RETENTION_MONTHS)


def purge_expired_completed_tasks(user, *, now=None) -> int:
    """Elimina tareas completadas hace más de dos meses del usuario."""

    cutoff = completed_task_cutoff(now)
    expired = Q(completada_en__lt=cutoff) | Q(
        completada_en__isnull=True,
        actualizada_en__lt=cutoff,
    )
    deleted, _ = Tarea.objects.filter(
        expired,
        usuario=user,
        estado=Tarea.Estado.COMPLETADA,
    ).delete()
    return deleted
