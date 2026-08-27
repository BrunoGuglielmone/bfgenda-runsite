"""Vistas de copias de seguridad, restauración y exportación."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from agenda.forms import ImportarCalendarioForm
from agenda.services.backups import (
    BACKUP_MANUAL,
    BackupError,
    create_backup,
    get_backup,
    restore_backup,
)
from agenda.services.exports import build_csv_export, build_json_export
from agenda.services.icalendar_io import (
    CalendarImportError,
    build_ics_export,
    import_ics_events,
)

from .common import (
    ConfirmationViewConfig,
    FormViewConfig,
    confirmation_response,
    form_response,
    get_return_url,
    is_ajax,
    saved_response,
)


def _backup_or_404(backup_name):
    try:
        return get_backup(backup_name)
    except BackupError as error:
        raise Http404(str(error)) from error


def _error_response(request, message, *, status=500):
    if is_ajax(request):
        return JsonResponse(
            {"ok": False, "message": message},
            status=status,
        )

    return HttpResponse(message, status=status, content_type="text/plain; charset=utf-8")


@login_required
@require_POST
def backup_crear(request):
    """Crea una copia manual utilizando la API de respaldo de SQLite."""

    return_url = get_return_url(request, reverse("agenda:configuracion"))

    try:
        backup = create_backup(BACKUP_MANUAL)
    except BackupError as error:
        return _error_response(request, str(error))

    return saved_response(
        request,
        message=f"Copia manual creada: {backup.name}",
        redirect_url=return_url,
        created=True,
    )


@login_required
@require_GET
def backup_descargar(request, backup_name):
    """Descarga una copia existente sin exponer rutas del sistema."""

    backup = _backup_or_404(backup_name)
    return FileResponse(
        backup.path.open("rb"),
        as_attachment=True,
        filename=backup.name,
        content_type="application/vnd.sqlite3",
    )


@login_required
@require_http_methods(["GET", "POST"])
def backup_restaurar(request, backup_name):
    """Confirma y restaura una copia local validada."""

    backup = _backup_or_404(backup_name)
    fallback = reverse("agenda:configuracion")
    return_url = get_return_url(request, fallback)

    if request.method == "POST":
        try:
            result = restore_backup(backup.name)
        except BackupError as error:
            return _error_response(request, str(error))

        request.session.flush()
        login_url = reverse("login")
        message = (
            f"Se restauró {result.restored_backup.name}. "
            "BFGenda guardó una copia preventiva del estado anterior."
        )

        if is_ajax(request):
            return JsonResponse(
                {
                    "ok": True,
                    "message": message,
                    "hard_reload": True,
                    "redirect_url": login_url,
                }
            )

        return redirect(login_url)

    config = ConfirmationViewConfig(
        eyebrow="Restaurar copia",
        title="¿Reemplazar los datos actuales?",
        description=(
            f"BFGenda volverá al estado guardado en {backup.name}. "
            "Las modificaciones posteriores a esa copia dejarán de estar activas."
        ),
        icon="↶",
        confirm_label="Restaurar y volver a iniciar sesión",
        cancel_url=return_url,
        action_url=reverse(
            "agenda:backup_restaurar",
            args=[backup.name],
        ),
        warning=(
            "La restauración reemplaza toda la base de datos, incluidos usuarios, "
            "tareas, eventos, categorías, preferencias y sesiones."
        ),
        details=(
            f"Tipo: {backup.kind_label}.",
            f"Fecha: {backup.created_at:%d/%m/%Y %H:%M}.",
            f"Tamaño: {backup.size_label}.",
            "Antes del reemplazo se creará automáticamente una copia preventiva.",
        ),
        hidden_fields=({"name": "return_url", "value": return_url},),
    )
    return confirmation_response(request, config)


def _export_response(export_file):
    response = HttpResponse(
        export_file.content,
        content_type=export_file.content_type,
    )
    response["Content-Disposition"] = (
        f'attachment; filename="{export_file.filename}"'
    )
    response["Content-Length"] = str(len(export_file.content))
    return response


@login_required
@require_GET
def exportar_json(request):
    """Descarga tareas, eventos, categorías y preferencias en JSON."""

    return _export_response(build_json_export(request.user))


@login_required
@require_GET
def exportar_csv(request):
    """Descarga un ZIP con archivos CSV separados por tipo de dato."""

    return _export_response(build_csv_export(request.user))


def _calendar_import_form_config(*, cancel_url: str) -> FormViewConfig:
    return FormViewConfig(
        eyebrow="Calendario iCalendar",
        title="Importar eventos",
        description=(
            "Agrega eventos desde un archivo .ics. BFGenda evita duplicados y "
            "omite reglas recurrentes que todavía no puede administrar como serie."
        ),
        icon="⇩",
        submit_label="Importar calendario",
        cancel_url=cancel_url,
        hidden_fields=(
            {"name": "return_url", "value": cancel_url},
        ),
    )


@login_required
@require_GET
def exportar_ics(request):
    """Descarga todos los eventos del usuario en formato iCalendar."""

    return _export_response(build_ics_export(request.user))


@login_required
@require_http_methods(["GET", "POST"])
def importar_ics(request):
    """Importa eventos simples desde un archivo iCalendar."""

    fallback = reverse("agenda:configuracion")
    return_url = get_return_url(request, fallback)
    config = _calendar_import_form_config(cancel_url=return_url)

    if request.method == "POST":
        form = ImportarCalendarioForm(
            request.POST,
            request.FILES,
            usuario=request.user,
        )

        if form.is_valid():
            try:
                result = import_ics_events(
                    request.user,
                    form.cleaned_data["archivo"],
                    category=form.cleaned_data.get("categoria"),
                )
            except CalendarImportError as error:
                form.add_error("archivo", str(error))
            else:
                return saved_response(
                    request,
                    message=result.message,
                    redirect_url=return_url,
                    created=result.imported > 0,
                )

        return form_response(request, form, config, invalid=True)

    form = ImportarCalendarioForm(usuario=request.user)
    return form_response(request, form, config)

