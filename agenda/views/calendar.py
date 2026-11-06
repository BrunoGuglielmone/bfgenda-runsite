from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from agenda.services.calendar import build_calendar_context, calendar_items_for_day
from agenda.services.event_queries import event_list_url
from agenda.services.preferences import get_user_preferences
from agenda.services.task_queries import task_list_url
from agenda.utils.dates import VALID_CALENDAR_VIEWS, parse_day

from .common import modal_content_response


@login_required
def calendario(request):
    """Muestra el calendario en vista diaria, semanal o mensual."""

    preferences = get_user_preferences(request.user)
    requested_view = request.GET.get("vista")
    view_value = (
        requested_view
        if requested_view in VALID_CALENDAR_VIEWS
        else preferences.vista_calendario
    )
    context = build_calendar_context(
        request.user,
        view_value=view_value,
        month_value=request.GET.get("mes"),
        day_value=request.GET.get("dia"),
    )
    return render(request, "agenda/calendario.html", context)


@login_required
def calendario_dia_resumen(request):
    """Muestra las tareas y eventos de un día sin permitir editarlos."""

    selected_day = parse_day(request.GET.get("fecha"), timezone.localdate())
    items = calendar_items_for_day(request.user, selected_day)
    readable_items = [
        {
            "titulo": item["titulo"],
            "meta": " · ".join(
                value
                for value in (
                    item["detalle_hora"],
                    item["estado"],
                )
                if value
            ),
            "secundario": None,
            "color": item["color"],
            "categoria": item["categoria"],
            "categoria_color": item["color"],
            "tipo": item["tipo_etiqueta"],
            "tipo_clase": item["tipo"],
            "url": item["url"],
            "destino": item["accion_etiqueta"],
            "completado": False,
        }
        for item in items
    ]
    fallback_url = reverse(
        "agenda:calendario",
        query={
            "vista": "dia",
            "dia": selected_day.isoformat(),
        },
    )
    context = {
        "modal_config": {
            "eyebrow": "Agenda del día",
            "title": selected_day.strftime("%d/%m/%Y"),
            "description": "Consulta todo lo programado para este día.",
            "icon": "▦",
            "empty_message": "No hay tareas ni eventos para este día.",
            "footer_note": "La edición se realiza únicamente desde Tareas o Eventos.",
        },
        "elementos": readable_items,
        "cantidad_total": len(readable_items),
        "cantidad_oculta": 0,
        "acciones": (
            {"url": task_list_url("pendientes"), "label": "Abrir Tareas"},
            {"url": event_list_url("todos"), "label": "Abrir Eventos"},
        ),
    }
    return modal_content_response(
        request,
        template_name="agenda/modales/listado_lectura.html",
        context=context,
        fallback_url=fallback_url,
    )
