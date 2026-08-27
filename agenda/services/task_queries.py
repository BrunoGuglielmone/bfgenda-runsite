from dataclasses import dataclass, replace
from datetime import date, timedelta

from django.db.models import Count, F, Q, QuerySet
from django.urls import reverse
from django.utils import timezone

from agenda.models import Tarea


DEFAULT_UNDATED_TASK_REMINDER_DAYS = 7
# Conserva compatibilidad con código y pruebas anteriores.
UNDATED_TASK_REMINDER_DAYS = DEFAULT_UNDATED_TASK_REMINDER_DAYS
UNDATED_REMINDER_SESSION_KEY = "agenda_undated_reminder_date"


@dataclass(frozen=True)
class TaskSummaryConfig:
    """Presentación y filtro de una vista rápida de tareas."""

    key: str
    title: str
    description: str
    icon: str
    filter_name: str
    empty_message: str
    list_filter_name: str | None = None


TASK_FILTERS = {
    "todas",
    "pendientes",
    "hoy",
    "semana",
    "proximas",
    "sin_fecha",
    "sin_fecha_olvidadas",
    "vencidas",
    "completadas",
}

TASK_SUMMARIES = {
    "pendientes": TaskSummaryConfig(
        key="pendientes",
        title="Tareas pendientes",
        description="Todo lo que todavía requiere tu atención.",
        icon="○",
        filter_name="pendientes",
        empty_message="No tienes tareas pendientes.",
    ),
    "vencidas": TaskSummaryConfig(
        key="vencidas",
        title="Tareas vencidas",
        description="Tareas cuya fecha límite ya pasó y siguen abiertas.",
        icon="!",
        filter_name="vencidas",
        empty_message="No tienes tareas vencidas.",
    ),
    "semana": TaskSummaryConfig(
        key="semana",
        title="Tareas de esta semana",
        description="Tareas pendientes comprendidas en la semana actual.",
        icon="▦",
        filter_name="semana",
        empty_message="No tienes tareas pendientes esta semana.",
    ),
    "completadas": TaskSummaryConfig(
        key="completadas",
        title="Tareas realizadas",
        description="Historial reciente de tareas completadas.",
        icon="✓",
        filter_name="completadas",
        empty_message="Todavía no tienes tareas realizadas en el historial reciente.",
    ),
    "sin_fecha_olvidadas": TaskSummaryConfig(
        key="sin_fecha_olvidadas",
        title="Tareas sin fecha que podrías estar olvidando",
        description="Tareas antiguas que continúan en la bandeja sin una fecha asignada.",
        icon="⌛",
        filter_name="sin_fecha_olvidadas",
        list_filter_name="sin_fecha",
        empty_message="No tienes tareas antiguas sin fecha.",
    ),
}


def week_bounds(today: date) -> tuple[date, date]:
    start = today - timedelta(days=today.weekday())
    return start, start + timedelta(days=6)


def normalize_task_filter(value: str | None) -> str:
    return value if value in TASK_FILTERS else "pendientes"


def task_list_url(filter_name: str, task_id: int | None = None) -> str:
    current_filter = normalize_task_filter(filter_name)

    if current_filter == "sin_fecha_olvidadas":
        current_filter = "sin_fecha"

    fragment = f"tarea-{task_id}" if task_id is not None else None
    return reverse(
        "agenda:tareas_listado",
        query={"filtro": current_filter},
        fragment=fragment,
    )


def user_tasks(user) -> QuerySet:
    return Tarea.objects.filter(usuario=user).select_related("categoria")


def task_queryset_for_filter(
    user,
    filter_name: str,
    *,
    today: date | None = None,
    reminder_days: int = DEFAULT_UNDATED_TASK_REMINDER_DAYS,
) -> QuerySet:
    today = today or timezone.localdate()
    current_filter = normalize_task_filter(filter_name)
    tasks = user_tasks(user)
    pending = ~Q(estado=Tarea.Estado.COMPLETADA)

    if current_filter == "pendientes":
        tasks = tasks.filter(pending)
    elif current_filter == "hoy":
        tasks = tasks.filter(pending, fecha_limite=today)
    elif current_filter == "semana":
        start_week, end_week = week_bounds(today)
        tasks = tasks.filter(
            pending,
            fecha_limite__range=(start_week, end_week),
        )
    elif current_filter == "proximas":
        tasks = tasks.filter(pending, fecha_limite__gt=today)
    elif current_filter == "sin_fecha":
        tasks = tasks.filter(pending, fecha_limite__isnull=True)
    elif current_filter == "sin_fecha_olvidadas":
        cutoff = timezone.now() - timedelta(days=reminder_days)
        tasks = tasks.filter(
            pending,
            fecha_limite__isnull=True,
            creada_en__lte=cutoff,
        )
    elif current_filter == "vencidas":
        tasks = tasks.filter(pending, fecha_limite__lt=today)
    elif current_filter == "completadas":
        return tasks.filter(
            estado=Tarea.Estado.COMPLETADA,
        ).order_by("-completada_en", "-actualizada_en")

    return tasks.order_by(
        F("fecha_limite").asc(nulls_last=True),
        "hora_limite",
        "-creada_en",
    )


def task_counts(
    user,
    *,
    today: date | None = None,
    reminder_days: int = DEFAULT_UNDATED_TASK_REMINDER_DAYS,
) -> dict[str, int]:
    today = today or timezone.localdate()
    start_week, end_week = week_bounds(today)
    cutoff = timezone.now() - timedelta(days=reminder_days)
    pending = ~Q(estado=Tarea.Estado.COMPLETADA)

    return Tarea.objects.filter(usuario=user).aggregate(
        cantidad_todas=Count("id"),
        cantidad_pendientes=Count("id", filter=pending),
        cantidad_hoy=Count("id", filter=pending & Q(fecha_limite=today)),
        cantidad_semana=Count(
            "id",
            filter=pending & Q(fecha_limite__range=(start_week, end_week)),
        ),
        cantidad_proximas=Count(
            "id",
            filter=pending & Q(fecha_limite__gt=today),
        ),
        cantidad_sin_fecha=Count(
            "id",
            filter=pending & Q(fecha_limite__isnull=True),
        ),
        cantidad_sin_fecha_olvidadas=Count(
            "id",
            filter=(
                pending
                & Q(fecha_limite__isnull=True)
                & Q(creada_en__lte=cutoff)
            ),
        ),
        cantidad_vencidas=Count(
            "id",
            filter=pending & Q(fecha_limite__lt=today),
        ),
        cantidad_completadas=Count(
            "id",
            filter=Q(estado=Tarea.Estado.COMPLETADA),
        ),
    )


def get_task_summary_config(
    value: str | None,
    *,
    reminder_days: int = DEFAULT_UNDATED_TASK_REMINDER_DAYS,
) -> TaskSummaryConfig | None:
    summary = TASK_SUMMARIES.get(value or "")

    if summary is None or summary.key != "sin_fecha_olvidadas":
        return summary

    unit = "día" if reminder_days == 1 else "días"
    return replace(
        summary,
        description=(
            f"Llevan al menos {reminder_days} {unit} en la bandeja "
            "sin una fecha asignada."
        ),
    )
