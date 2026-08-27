import logging

from django.shortcuts import render
from django.utils import timezone

from agenda.services.backups import (
    AUTO_BACKUP_SESSION_KEY,
    BackupError,
    ensure_daily_backup,
)
from agenda.services.maintenance import (
    leave_request,
    try_enter_request,
)
from agenda.services.retention import (
    CLEANUP_SESSION_KEY,
    purge_expired_completed_tasks,
)


logger = logging.getLogger(__name__)


class MaintenanceMiddleware:
    """
    Impide nuevas solicitudes mientras se reemplaza la base SQLite.

    Se coloca antes de SessionMiddleware para no consultar la base de
    datos durante una restauracion.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not try_enter_request():
            response = render(
                request,
                "registration/mantenimiento.html",
                status=503,
            )
            response["Retry-After"] = "3"
            response["Cache-Control"] = "no-store"
            return response

        try:
            return self.get_response(request)
        finally:
            leave_request()


class CompletedTaskRetentionMiddleware:
    """Ejecuta una vez al día el mantenimiento local de BFGenda."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)

        if user is not None and user.is_authenticated:
            today_key = timezone.localdate().isoformat()

            if request.session.get(CLEANUP_SESSION_KEY) != today_key:
                purge_expired_completed_tasks(user)
                request.session[CLEANUP_SESSION_KEY] = today_key

            if request.session.get(AUTO_BACKUP_SESSION_KEY) != today_key:
                try:
                    ensure_daily_backup()
                except BackupError:
                    logger.exception(
                        "No se pudo crear la copia automática diaria de BFGenda."
                    )
                finally:
                    request.session[AUTO_BACKUP_SESSION_KEY] = today_key

        return self.get_response(request)
