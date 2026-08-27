from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.db.models import Count, Q, QuerySet
from django.urls import reverse
from django.utils import timezone

from agenda.models import Evento


@dataclass(frozen=True)
class EventSummaryConfig:
    """Presentación y filtro de una vista rápida de eventos."""

    key: str
    title: str
    description: str
    icon: str
    filter_name: str
    empty_message: str


EVENT_FILTERS = {
    "todos",
    "hoy",
    "semana",
    "proximos",
    "pasados",
    "cancelados",
}

EVENT_SUMMARIES = {
    "hoy": EventSummaryConfig(
        key="hoy",
        title="Eventos de hoy",
        description="Compromisos que ocurren durante la jornada actual.",
        icon="◷",
        filter_name="hoy",
        empty_message="No tienes eventos para hoy.",
    ),
    "semana": EventSummaryConfig(
        key="semana",
        title="Eventos de esta semana",
        description="Eventos comprendidos en la semana actual.",
        icon="▦",
        filter_name="semana",
        empty_message="No tienes eventos esta semana.",
    ),
    "proximos": EventSummaryConfig(
        key="proximos",
        title="Eventos próximos",
        description="Tus próximos compromisos.",
        icon="→",
        filter_name="proximos",
        empty_message="No tienes eventos próximos.",
    ),
}


def _aware_day_bounds(day: date):
    current_tz = timezone.get_current_timezone()
    start = timezone.make_aware(
        datetime.combine(day, time.min),
        current_tz,
    )
    return start, start + timedelta(days=1)


def _aware_week_bounds(day: date):
    week_start = day - timedelta(days=day.weekday())
    week_end = week_start + timedelta(days=7)
    current_tz = timezone.get_current_timezone()
    start = timezone.make_aware(
        datetime.combine(week_start, time.min),
        current_tz,
    )
    end = timezone.make_aware(
        datetime.combine(week_end, time.min),
        current_tz,
    )
    return start, end


def normalize_event_filter(value: str | None) -> str:
    return value if value in EVENT_FILTERS else "proximos"


def event_list_url(
    filter_name: str,
    event_id: int | None = None,
) -> str:
    current_filter = normalize_event_filter(filter_name)
    fragment = (
        f"evento-{event_id}"
        if event_id is not None
        else None
    )
    return reverse(
        "agenda:eventos_listado",
        query={"filtro": current_filter},
        fragment=fragment,
    )


def user_events(user) -> QuerySet:
    return (
        Evento.objects
        .filter(usuario=user)
        .select_related("categoria")
    )


def event_queryset_for_filter(
    user,
    filter_name: str,
    *,
    today: date | None = None,
    now=None,
) -> QuerySet:
    today = today or timezone.localdate()
    now = now or timezone.now()
    current_filter = normalize_event_filter(filter_name)
    events = user_events(user)
    start_today, start_tomorrow = _aware_day_bounds(today)
    not_cancelled = ~Q(estado=Evento.Estado.CANCELADO)

    if current_filter == "hoy":
        events = events.filter(
            not_cancelled,
            inicio__lt=start_tomorrow,
            fin__gt=start_today,
        )
    elif current_filter == "semana":
        start_week, end_week = _aware_week_bounds(today)
        events = events.filter(
            not_cancelled,
            inicio__lt=end_week,
            fin__gt=start_week,
        )
    elif current_filter == "proximos":
        events = events.filter(
            not_cancelled,
            inicio__gte=now,
        )
    elif current_filter == "pasados":
        events = events.filter(
            not_cancelled,
            fin__lt=now,
        )
    elif current_filter == "cancelados":
        events = events.filter(
            estado=Evento.Estado.CANCELADO,
        )

    return events.order_by("inicio", "fin", "titulo")


def event_counts(
    user,
    *,
    today: date | None = None,
    now=None,
) -> dict[str, int]:
    today = today or timezone.localdate()
    now = now or timezone.now()
    start_today, start_tomorrow = _aware_day_bounds(today)
    start_week, end_week = _aware_week_bounds(today)
    not_cancelled = ~Q(estado=Evento.Estado.CANCELADO)

    return Evento.objects.filter(usuario=user).aggregate(
        cantidad_eventos=Count("id"),
        cantidad_eventos_hoy=Count(
            "id",
            filter=(
                not_cancelled
                & Q(
                    inicio__lt=start_tomorrow,
                    fin__gt=start_today,
                )
            ),
        ),
        cantidad_eventos_semana=Count(
            "id",
            filter=(
                not_cancelled
                & Q(
                    inicio__lt=end_week,
                    fin__gt=start_week,
                )
            ),
        ),
        cantidad_eventos_proximos=Count(
            "id",
            filter=not_cancelled & Q(inicio__gte=now),
        ),
        cantidad_eventos_pasados=Count(
            "id",
            filter=not_cancelled & Q(fin__lt=now),
        ),
        cantidad_eventos_cancelados=Count(
            "id",
            filter=Q(estado=Evento.Estado.CANCELADO),
        ),
    )


def get_event_summary_config(
    value: str | None,
) -> EventSummaryConfig | None:
    return EVENT_SUMMARIES.get(value or "")
