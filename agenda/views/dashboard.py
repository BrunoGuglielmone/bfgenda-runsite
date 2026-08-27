from datetime import datetime, time, timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from agenda.models import Evento
from agenda.services.event_queries import event_counts, event_queryset_for_filter
from agenda.services.preferences import get_user_preferences
from agenda.services.task_queries import (
    UNDATED_REMINDER_SESSION_KEY,
    task_counts,
    task_queryset_for_filter,
)


def _greeting() -> str:
    hour = timezone.localtime().hour

    if hour < 12:
        return "Buenos días"
    if hour < 20:
        return "Buenas tardes"
    return "Buenas noches"


@login_required
def inicio(request):
    """Muestra el resumen personal de tareas y eventos."""

    today = timezone.localdate()
    preferences = get_user_preferences(request.user)
    current_tz = timezone.get_current_timezone()
    start_today = timezone.make_aware(
        datetime.combine(today, time.min),
        current_tz,
    )
    start_tomorrow = start_today + timedelta(days=1)

    today_tasks = task_queryset_for_filter(request.user, "hoy", today=today)
    upcoming_tasks = task_queryset_for_filter(
        request.user,
        "proximas",
        today=today,
    )[:5]
    undated_tasks = task_queryset_for_filter(
        request.user,
        "sin_fecha",
        today=today,
    )[:5]
    counts = task_counts(
        request.user,
        today=today,
        reminder_days=preferences.dias_aviso_sin_fecha,
    )
    forgotten_tasks = counts["cantidad_sin_fecha_olvidadas"]

    scheduled_events = Evento.objects.filter(
        usuario=request.user,
        estado=Evento.Estado.PROGRAMADO,
    ).select_related("categoria")
    today_events = scheduled_events.filter(
        inicio__lt=start_tomorrow,
        fin__gt=start_today,
    ).order_by("inicio", "fin")
    upcoming_events = event_queryset_for_filter(
        request.user,
        "proximos",
        today=today,
    )[:5]
    event_summary_counts = event_counts(request.user, today=today)

    auto_modal_url = None
    today_key = today.isoformat()

    if (
        preferences.avisos_sin_fecha_activos
        and forgotten_tasks
        and request.session.get(UNDATED_REMINDER_SESSION_KEY) != today_key
    ):
        auto_modal_url = reverse(
            "agenda:tareas_resumen",
            query={"tipo": "sin_fecha_olvidadas"},
        )
        request.session[UNDATED_REMINDER_SESSION_KEY] = today_key

    context = {
        "fecha_actual": today,
        "saludo": _greeting(),
        "tareas_hoy": today_tasks,
        "tareas_proximas": upcoming_tasks,
        "tareas_sin_fecha": undated_tasks,
        "eventos_hoy": today_events,
        "eventos_proximos": upcoming_events,
        "auto_modal_url": auto_modal_url,
        **counts,
        **event_summary_counts,
    }

    return render(request, "agenda/inicio.html", context)
