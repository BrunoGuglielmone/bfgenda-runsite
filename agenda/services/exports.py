"""Exportación portable de los datos personales de BFGenda."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import dataclass

from django.utils import timezone

from agenda.models import Categoria, Evento, Tarea
from agenda.services.preferences import get_user_preferences


EXPORT_SCHEMA_VERSION = 1
CSV_DELIMITER = ";"


@dataclass(frozen=True)
class ExportFile:
    """Archivo generado listo para enviarse como respuesta HTTP."""

    content: bytes
    filename: str
    content_type: str


def _local_iso(value):
    if value is None:
        return None

    if hasattr(value, "tzinfo") and value.tzinfo is not None:
        value = timezone.localtime(value)

    return value.isoformat()


def _category_name(category) -> str:
    return category.nombre if category else "Sin categoría"


def build_json_payload(user) -> dict:
    """Construye un documento JSON limitado al usuario autenticado."""

    preferences = get_user_preferences(user)
    categories = Categoria.objects.filter(usuario=user).order_by("nombre")
    tasks = (
        Tarea.objects.filter(usuario=user)
        .select_related("categoria")
        .order_by("creada_en")
    )
    events = (
        Evento.objects.filter(usuario=user)
        .select_related("categoria")
        .order_by("inicio", "titulo")
    )

    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "application": "BFGenda",
        "exported_at": timezone.localtime().isoformat(),
        "user": {
            "username": user.get_username(),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
        },
        "preferences": {
            "calendar_default_view": preferences.vista_calendario,
            "new_event_start_time": preferences.hora_inicio_evento.isoformat(),
            "new_event_duration_minutes": preferences.duracion_evento_minutos,
            "undated_reminders_enabled": preferences.avisos_sin_fecha_activos,
            "undated_reminder_days": preferences.dias_aviso_sin_fecha,
        },
        "categories": [
            {
                "id": category.id,
                "name": category.nombre,
                "color": category.color,
                "active": category.activa,
                "created_at": _local_iso(category.creada_en),
                "updated_at": _local_iso(category.actualizada_en),
            }
            for category in categories
        ],
        "tasks": [
            {
                "id": task.id,
                "title": task.titulo,
                "description": task.descripcion,
                "due_date": _local_iso(task.fecha_limite),
                "due_time": _local_iso(task.hora_limite),
                "priority": task.prioridad,
                "priority_label": task.get_prioridad_display(),
                "status": task.estado,
                "status_label": task.get_estado_display(),
                "category": _category_name(task.categoria),
                "completed_at": _local_iso(task.completada_en),
                "created_at": _local_iso(task.creada_en),
                "updated_at": _local_iso(task.actualizada_en),
            }
            for task in tasks
        ],
        "events": [
            {
                "id": event.id,
                "title": event.titulo,
                "description": event.descripcion,
                "start": _local_iso(event.inicio),
                "end": _local_iso(event.fin),
                "all_day": event.todo_el_dia,
                "location": event.ubicacion,
                "status": event.estado,
                "status_label": event.get_estado_display(),
                "category": _category_name(event.categoria),
                "ical_uid": event.ical_uid,
                "created_at": _local_iso(event.creado_en),
                "updated_at": _local_iso(event.actualizado_en),
            }
            for event in events
        ],
    }


def build_json_export(user) -> ExportFile:
    """Genera una exportación JSON legible y codificada en UTF-8."""

    now = timezone.localtime()
    payload = build_json_payload(user)
    content = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=False,
    ).encode("utf-8")
    return ExportFile(
        content=content,
        filename=f"bfgenda-datos-{now:%Y%m%d-%H%M%S}.json",
        content_type="application/json; charset=utf-8",
    )


def _csv_bytes(headers, rows) -> bytes:
    text = io.StringIO(newline="")
    writer = csv.writer(
        text,
        delimiter=CSV_DELIMITER,
        quoting=csv.QUOTE_MINIMAL,
        lineterminator="\r\n",
    )
    writer.writerow(headers)
    writer.writerows(rows)
    return text.getvalue().encode("utf-8-sig")


def build_csv_export(user) -> ExportFile:
    """Genera un ZIP con CSV separados y compatibles con Excel."""

    now = timezone.localtime()
    preferences = get_user_preferences(user)
    categories = list(Categoria.objects.filter(usuario=user).order_by("nombre"))
    tasks = list(
        Tarea.objects.filter(usuario=user)
        .select_related("categoria")
        .order_by("creada_en")
    )
    events = list(
        Evento.objects.filter(usuario=user)
        .select_related("categoria")
        .order_by("inicio", "titulo")
    )

    files = {
        "categorias.csv": _csv_bytes(
            ("ID", "Nombre", "Color", "Activa", "Creada", "Actualizada"),
            (
                (
                    category.id,
                    category.nombre,
                    category.color,
                    "Sí" if category.activa else "No",
                    _local_iso(category.creada_en),
                    _local_iso(category.actualizada_en),
                )
                for category in categories
            ),
        ),
        "tareas.csv": _csv_bytes(
            (
                "ID",
                "Título",
                "Descripción",
                "Fecha límite",
                "Hora límite",
                "Prioridad",
                "Estado",
                "Categoría",
                "Completada",
                "Creada",
                "Actualizada",
            ),
            (
                (
                    task.id,
                    task.titulo,
                    task.descripcion,
                    _local_iso(task.fecha_limite),
                    _local_iso(task.hora_limite),
                    task.get_prioridad_display(),
                    task.get_estado_display(),
                    _category_name(task.categoria),
                    _local_iso(task.completada_en),
                    _local_iso(task.creada_en),
                    _local_iso(task.actualizada_en),
                )
                for task in tasks
            ),
        ),
        "eventos.csv": _csv_bytes(
            (
                "ID",
                "Título",
                "Descripción",
                "Inicio",
                "Finalización",
                "Todo el día",
                "Ubicación",
                "Estado",
                "Categoría",
                "UID iCalendar",
                "Creado",
                "Actualizado",
            ),
            (
                (
                    event.id,
                    event.titulo,
                    event.descripcion,
                    _local_iso(event.inicio),
                    _local_iso(event.fin),
                    "Sí" if event.todo_el_dia else "No",
                    event.ubicacion,
                    event.get_estado_display(),
                    _category_name(event.categoria),
                    event.ical_uid or "",
                    _local_iso(event.creado_en),
                    _local_iso(event.actualizado_en),
                )
                for event in events
            ),
        ),
        "preferencias.csv": _csv_bytes(
            ("Preferencia", "Valor"),
            (
                ("Vista inicial del calendario", preferences.get_vista_calendario_display()),
                ("Hora inicial de eventos", preferences.hora_inicio_evento.isoformat()),
                ("Duración inicial en minutos", preferences.duracion_evento_minutos),
                (
                    "Avisos de tareas sin fecha",
                    "Activos" if preferences.avisos_sin_fecha_activos else "Desactivados",
                ),
                ("Días para aviso sin fecha", preferences.dias_aviso_sin_fecha),
            ),
        ),
    }

    archive = io.BytesIO()

    with zipfile.ZipFile(
        archive,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as zip_file:
        for filename, content in files.items():
            zip_file.writestr(filename, content)

        zip_file.writestr(
            "LEEME.txt",
            (
                "Exportación de BFGenda\r\n"
                f"Fecha: {now:%d/%m/%Y %H:%M}\r\n"
                "Los archivos usan UTF-8 y punto y coma como separador.\r\n"
                "Esta exportación sirve para consulta y traslado de datos; "
                "la copia SQLite es la opción indicada para restaurar BFGenda.\r\n"
            ).encode("utf-8-sig"),
        )

    return ExportFile(
        content=archive.getvalue(),
        filename=f"bfgenda-csv-{now:%Y%m%d-%H%M%S}.zip",
        content_type="application/zip",
    )
