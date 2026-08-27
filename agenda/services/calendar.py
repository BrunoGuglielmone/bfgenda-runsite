import calendar
from datetime import date, datetime, time, timedelta

from django.urls import reverse
from django.utils import timezone

from agenda.models import Evento, Tarea
from agenda.services.event_queries import event_list_url
from agenda.services.task_queries import task_counts, task_list_url
from agenda.utils.dates import (
    add_months,
    calendar_url_for_view,
    normalize_calendar_view,
    parse_day,
    parse_month,
    shift_months,
)


MONTH_NAMES = (
    "",
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)


def _category_data(category):
    if category:
        return category.color, category.nombre
    return "#9A9EAD", "Sin categoría"


def _task_item(task):
    color, category = _category_data(task.categoria)
    hour_text = task.hora_limite.strftime("%H:%M") if task.hora_limite else "Sin hora"
    series_delete_url = (
        reverse("agenda:tarea_serie_eliminar", args=[task.id])
        if task.serie_recurrencia
        else None
    )
    return {
        "tipo": "tarea",
        "tipo_etiqueta": "Tarea",
        "titulo": task.titulo,
        "hora": hour_text,
        "detalle_hora": hour_text,
        "categoria": category,
        "color": color,
        "estado": task.get_estado_display(),
        "url": task_list_url("pendientes", task.id),
        "modal_url": None,
        "accion_etiqueta": "Ver en Tareas →",
        "serie_eliminar_url": series_delete_url,
        "recurrencia_etiqueta": (
            f"Serie {task.get_tipo_recurrencia_display().lower()}"
            if task.serie_recurrencia
            else None
        ),
        "orden": (2, task.hora_limite or time.max, task.titulo.lower()),
    }


def _event_item(event, start_local, end_local, visual_end):
    start_date = start_local.date()
    end_date = visual_end.date()
    color, category = _category_data(event.categoria)
    series_delete_url = (
        reverse("agenda:evento_serie_eliminar", args=[event.id])
        if event.serie_recurrencia
        else None
    )

    if event.todo_el_dia:
        hour_text = "Todo el día"
        detail_text = "Todo el día"
        sort_key = (0, time.min, event.titulo.lower())
    else:
        hour_text = start_local.strftime("%H:%M")
        detail_text = (
            f"{start_local:%H:%M}–{end_local:%H:%M}"
            if start_date == end_date
            else f"{start_local:%d/%m %H:%M} – {end_local:%d/%m %H:%M}"
        )
        sort_key = (1, start_local.time(), event.titulo.lower())

    return {
        "tipo": "evento",
        "tipo_etiqueta": "Evento",
        "titulo": event.titulo,
        "hora": hour_text,
        "detalle_hora": detail_text,
        "categoria": category,
        "color": color,
        "estado": event.get_estado_display(),
        "url": event_list_url("todos", event.id),
        "modal_url": None,
        "accion_etiqueta": "Ver en Eventos →",
        "serie_eliminar_url": series_delete_url,
        "recurrencia_etiqueta": (
            f"Serie {event.get_tipo_recurrencia_display().lower()}"
            if event.serie_recurrencia
            else None
        ),
        "orden": sort_key,
    }


def _range_datetimes(first_date: date, last_date: date):
    current_tz = timezone.get_current_timezone()
    range_start = timezone.make_aware(
        datetime.combine(first_date, time.min),
        current_tz,
    )
    range_end = timezone.make_aware(
        datetime.combine(last_date + timedelta(days=1), time.min),
        current_tz,
    )
    return current_tz, range_start, range_end


def _items_by_day(user, first_date: date, last_date: date):
    """Carga tareas y eventos una sola vez para un intervalo de fechas."""

    day_count = (last_date - first_date).days + 1
    visible_dates = {
        first_date + timedelta(days=offset)
        for offset in range(day_count)
    }
    items_by_day = {value: [] for value in visible_dates}
    current_tz, range_start, range_end = _range_datetimes(first_date, last_date)

    tasks = (
        Tarea.objects.filter(
            usuario=user,
            fecha_limite__range=(first_date, last_date),
        )
        .exclude(estado=Tarea.Estado.COMPLETADA)
        .select_related("categoria")
        .order_by("fecha_limite", "hora_limite", "titulo")
    )

    for task in tasks:
        items_by_day[task.fecha_limite].append(_task_item(task))

    events = (
        Evento.objects.filter(
            usuario=user,
            inicio__lt=range_end,
            fin__gt=range_start,
        )
        .select_related("categoria")
        .order_by("inicio", "fin", "titulo")
    )

    for event in events:
        start_local = timezone.localtime(event.inicio, current_tz)
        end_local = timezone.localtime(event.fin, current_tz)
        visual_end = end_local

        if end_local > start_local and end_local.time() == time.min:
            visual_end = end_local - timedelta(microseconds=1)

        item = _event_item(event, start_local, end_local, visual_end)
        current_date = max(start_local.date(), first_date)
        end_date = min(visual_end.date(), last_date)

        while current_date <= end_date:
            items_by_day[current_date].append(item)
            current_date += timedelta(days=1)

    for items in items_by_day.values():
        items.sort(key=lambda item: item["orden"])

    return items_by_day


def calendar_items_for_day(user, selected_day: date):
    """Devuelve los elementos normalizados de un único día."""

    return _items_by_day(user, selected_day, selected_day)[selected_day]


def calendar_day_summary_url(selected_day: date) -> str:
    return reverse(
        "agenda:calendario_dia_resumen",
        query={"fecha": selected_day.isoformat()},
    )


def _view_options(selected_day: date):
    return [
        {
            "value": view,
            "label": label,
            "url": calendar_url_for_view(view, selected_day),
        }
        for view, label in (
            ("dia", "Día"),
            ("semana", "Semana"),
            ("mes", "Mes"),
        )
    ]


def _base_context(user, view: str, selected_day: date, today: date):
    if view == "dia":
        previous_date = selected_day - timedelta(days=1)
        next_date = selected_day + timedelta(days=1)
        period_title = (
            f"{selected_day.day} de {MONTH_NAMES[selected_day.month]} "
            f"de {selected_day.year}"
        )
    elif view == "semana":
        previous_date = selected_day - timedelta(days=7)
        next_date = selected_day + timedelta(days=7)
        week_start = selected_day - timedelta(days=selected_day.weekday())
        week_end = week_start + timedelta(days=6)
        period_title = f"Semana del {week_start:%d/%m} al {week_end:%d/%m/%Y}"
    else:
        previous_date = shift_months(selected_day, -1)
        next_date = shift_months(selected_day, 1)
        period_title = f"{MONTH_NAMES[selected_day.month]} {selected_day.year}"

    counts = task_counts(user, today=today)
    return {
        "vista_actual": view,
        "vistas_calendario": _view_options(selected_day),
        "dia_seleccionado": selected_day,
        "titulo_periodo": period_title,
        "url_periodo_anterior": calendar_url_for_view(view, previous_date),
        "url_periodo_siguiente": calendar_url_for_view(view, next_date),
        "url_hoy": calendar_url_for_view(view, today),
        "cantidad_completadas": counts["cantidad_completadas"],
    }


def _month_context(user, selected_day, month_value, today):
    viewed_month = parse_month(month_value, selected_day)
    month_calendar = calendar.Calendar(firstweekday=calendar.MONDAY)
    month_weeks = month_calendar.monthdatescalendar(
        viewed_month.year,
        viewed_month.month,
    )
    first_date = month_weeks[0][0]
    last_date = month_weeks[-1][-1]
    items_by_day = _items_by_day(user, first_date, last_date)

    if selected_day not in items_by_day:
        selected_day = (
            today
            if viewed_month.year == today.year
            and viewed_month.month == today.month
            else viewed_month
        )

    weeks = []

    for week in month_weeks:
        data_week = []

        for day in week:
            items = items_by_day[day]
            data_week.append(
                {
                    "fecha": day,
                    "es_mes_actual": day.month == viewed_month.month,
                    "es_hoy": day == today,
                    "seleccionado": day == selected_day,
                    "elementos": items,
                    "cantidad_extra": max(len(items) - 3, 0),
                    "url_mes": calendar_url_for_view("mes", day),
                    "modal_url": calendar_day_summary_url(day) if items else None,
                }
            )

        weeks.append(data_week)

    context = _base_context(user, "mes", selected_day, today)
    context.update(
        {
            "titulo_periodo": f"{MONTH_NAMES[viewed_month.month]} {viewed_month.year}",
            "mes_consultado": viewed_month,
            "mes_anterior": add_months(viewed_month, -1),
            "mes_siguiente": add_months(viewed_month, 1),
            "semanas": weeks,
            "elementos_dia_seleccionado": items_by_day[selected_day],
            "url_periodo_anterior": calendar_url_for_view(
                "mes",
                shift_months(selected_day, -1),
            ),
            "url_periodo_siguiente": calendar_url_for_view(
                "mes",
                shift_months(selected_day, 1),
            ),
        }
    )
    return context


def _week_context(user, selected_day, today):
    week_start = selected_day - timedelta(days=selected_day.weekday())
    week_end = week_start + timedelta(days=6)
    items_by_day = _items_by_day(user, week_start, week_end)
    days = []

    for offset in range(7):
        day = week_start + timedelta(days=offset)
        items = items_by_day[day]
        days.append(
            {
                "fecha": day,
                "es_hoy": day == today,
                "seleccionado": day == selected_day,
                "elementos": items,
                "elementos_visibles": items[:4],
                "cantidad_extra": max(len(items) - 4, 0),
                "url_dia": calendar_url_for_view("dia", day),
                "modal_url": calendar_day_summary_url(day) if items else None,
            }
        )

    context = _base_context(user, "semana", selected_day, today)
    context.update(
        {
            "inicio_semana": week_start,
            "fin_semana": week_end,
            "dias_semana": days,
        }
    )
    return context


def _day_context(user, selected_day, today):
    items_by_day = _items_by_day(user, selected_day, selected_day)
    context = _base_context(user, "dia", selected_day, today)
    context["elementos_dia_seleccionado"] = items_by_day[selected_day]
    return context


def build_calendar_context(
    user,
    *,
    view_value=None,
    month_value=None,
    day_value=None,
):
    """Construye una vista diaria, semanal o mensual del calendario."""

    today = timezone.localdate()
    view = normalize_calendar_view(view_value)
    selected_day = parse_day(day_value, today) or today

    if view == "dia":
        return _day_context(user, selected_day, today)
    if view == "semana":
        return _week_context(user, selected_day, today)
    return _month_context(user, selected_day, month_value, today)
