"""Calculo de recordatorios que debe mostrar un dispositivo."""

from datetime import datetime, timedelta

from django.urls import reverse
from django.utils import timezone

from agenda.models import Evento, Tarea
from agenda.services.preferences import get_user_preferences


REMINDER_LATE_TOLERANCE = timedelta(minutes=10)


def _aware_local_datetime(day, clock_time):
    """Construye una fecha y hora consciente en la zona activa."""

    current_timezone = timezone.get_current_timezone()
    naive_value = datetime.combine(day, clock_time)
    return timezone.make_aware(
        naive_value,
        current_timezone,
    )


def _is_due(reminder_at, *, now):
    """Indica si el aviso esta dentro de la ventana de entrega."""

    oldest_allowed = now - REMINDER_LATE_TOLERANCE
    return oldest_allowed <= reminder_at <= now


def _serialize_reminder(
    *,
    reminder_type,
    object_id,
    title,
    body,
    reminder_at,
    url,
):
    local_reminder = timezone.localtime(reminder_at)

    return {
        "id": f"{reminder_type}-{object_id}",
        "type": reminder_type,
        "title": title,
        "body": body,
        "tag": (
            f"bfgenda-{reminder_type}-{object_id}-"
            f"{local_reminder:%Y%m%d%H%M}"
        ),
        "url": url,
        "reminder_at": local_reminder.isoformat(),
    }


def _task_reminder_at(task, *, preferences):
    if task.fecha_limite is None:
        return None

    if task.hora_limite is not None:
        deadline = _aware_local_datetime(
            task.fecha_limite,
            task.hora_limite,
        )
        advance = timedelta(
            minutes=preferences.anticipacion_recordatorios_minutos
        )
        return deadline - advance

    return _aware_local_datetime(
        task.fecha_limite,
        preferences.hora_recordatorios_sin_hora,
    )


def _event_reminder_at(event, *, preferences):
    local_start = timezone.localtime(event.inicio)

    if event.todo_el_dia:
        return _aware_local_datetime(
            local_start.date(),
            preferences.hora_recordatorios_sin_hora,
        )

    advance = timedelta(
        minutes=preferences.anticipacion_eventos_minutos
    )
    return event.inicio - advance


def _collect_task_reminders(
    user,
    *,
    now,
    minimum_day,
    maximum_day,
    preferences,
):
    reminders = []

    tasks = (
        Tarea.objects
        .filter(
            usuario=user,
            fecha_limite__range=(minimum_day, maximum_day),
        )
        .exclude(estado=Tarea.Estado.COMPLETADA)
        .order_by("fecha_limite", "hora_limite", "id")
    )

    for task in tasks:
        reminder_at = _task_reminder_at(
            task,
            preferences=preferences,
        )

        if reminder_at is None or not _is_due(
            reminder_at,
            now=now,
        ):
            continue

        if task.hora_limite:
            local_deadline = timezone.localtime(
                _aware_local_datetime(
                    task.fecha_limite,
                    task.hora_limite,
                )
            )
            body = f"Vence hoy a las {local_deadline:%H:%M}."
        else:
            body = "Esta tarea vence hoy."

        reminders.append(
            _serialize_reminder(
                reminder_type="task",
                object_id=task.id,
                title=task.titulo,
                body=body,
                reminder_at=reminder_at,
                url=reverse("agenda:tareas_listado"),
            )
        )

    return reminders


def _collect_event_reminders(
    user,
    *,
    now,
    minimum_day,
    maximum_day,
    preferences,
):
    reminders = []

    events = (
        Evento.objects
        .filter(
            usuario=user,
            estado=Evento.Estado.PROGRAMADO,
            inicio__date__range=(minimum_day, maximum_day),
        )
        .order_by("inicio", "id")
    )

    for event in events:
        reminder_at = _event_reminder_at(
            event,
            preferences=preferences,
        )

        if not _is_due(reminder_at, now=now):
            continue

        local_start = timezone.localtime(event.inicio)

        if event.todo_el_dia:
            body = "Evento programado para hoy."
        else:
            body = f"Comienza a las {local_start:%H:%M}."

        if event.ubicacion:
            body = f"{body} {event.ubicacion}"

        reminders.append(
            _serialize_reminder(
                reminder_type="event",
                object_id=event.id,
                title=event.titulo,
                body=body,
                reminder_at=reminder_at,
                url=reverse("agenda:eventos_listado"),
            )
        )

    return reminders


def collect_due_reminders(user, *, now=None):
    """Devuelve los avisos vencidos recientemente para un usuario."""

    now = now or timezone.now()
    local_now = timezone.localtime(now)
    minimum_day = local_now.date() - timedelta(days=1)
    maximum_day = local_now.date() + timedelta(days=1)
    preferences = get_user_preferences(user)
    reminders = []

    if preferences.recordatorios_tareas_activos:
        reminders.extend(
            _collect_task_reminders(
                user,
                now=now,
                minimum_day=minimum_day,
                maximum_day=maximum_day,
                preferences=preferences,
            )
        )

    if preferences.recordatorios_eventos_activos:
        reminders.extend(
            _collect_event_reminders(
                user,
                now=now,
                minimum_day=minimum_day,
                maximum_day=maximum_day,
                preferences=preferences,
            )
        )

    reminders.sort(key=lambda item: item["reminder_at"])
    return reminders
