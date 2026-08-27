from datetime import datetime, time, timedelta

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from agenda.forms import EventoForm
from agenda.models import Evento
from agenda.services.event_queries import (
    event_counts,
    event_list_url,
    event_queryset_for_filter,
    get_event_summary_config,
    normalize_event_filter,
)
from agenda.services.preferences import get_user_preferences
from agenda.services.read_items import event_read_item
from agenda.services.recurrence import (
    REPEAT_MONTHLY,
    create_recurring_events,
    normalize_repeat_mode,
    repeat_mode_plural,
)
from agenda.utils.dates import calendar_url_for_date, parse_day

from .common import (
    ConfirmationViewConfig,
    FormViewConfig,
    confirmation_response,
    form_response,
    get_return_url,
    modal_content_response,
    saved_response,
)


MODAL_EVENT_LIMIT = 40


def _repeat_mode(request):
    value = request.POST.get("repetir") or request.GET.get("repetir")
    return normalize_repeat_mode(value)


def _event_form_config(
    *,
    editing: bool,
    repeat_mode=None,
    cancel_url: str,
    hidden_fields=(),
):
    if editing:
        title = "Editar evento"
        description = "Modifica la fecha, el horario, el estado o cualquier otra información."
        eyebrow = "Evento"
        icon = "▦"
        submit_label = "Guardar cambios"
    elif repeat_mode == REPEAT_MONTHLY:
        title = "Nuevo evento mensual"
        description = (
            "Crea un evento independiente para el mismo número de día de cada mes "
            "hasta la fecha que elijas."
        )
        eyebrow = "Evento mensual"
        icon = "↻"
        submit_label = "Guardar eventos"
    elif repeat_mode:
        title = "Nuevo evento semanal"
        description = (
            "Crea un evento independiente para el mismo día de cada semana "
            "hasta la fecha que elijas."
        )
        eyebrow = "Evento semanal"
        icon = "↻"
        submit_label = "Guardar eventos"
    else:
        title = "Nuevo evento"
        description = "Registra una actividad o compromiso con fecha y horario."
        eyebrow = "Evento"
        icon = "▦"
        submit_label = "Guardar evento"

    return FormViewConfig(
        eyebrow=eyebrow,
        title=title,
        description=description,
        icon=icon,
        submit_label=submit_label,
        cancel_url=cancel_url,
        hidden_fields=tuple(hidden_fields),
    )


@login_required
def eventos_listado(request):
    """Listado único desde el que se crean y editan eventos."""

    today = timezone.localdate()
    current_filter = normalize_event_filter(request.GET.get("filtro"))
    events = event_queryset_for_filter(
        request.user,
        current_filter,
        today=today,
    )
    counts = event_counts(request.user, today=today)

    context = {
        "fecha_actual": today,
        "filtro_actual": current_filter,
        "eventos": events,
        "cantidad_resultados": events.count(),
        **counts,
    }
    return render(request, "agenda/eventos_listado.html", context)


@login_required
def eventos_resumen(request):
    """Vista rápida de solo lectura para eventos."""

    summary = get_event_summary_config(request.GET.get("tipo"))

    if summary is None:
        raise Http404("El resumen de eventos solicitado no existe.")

    today = timezone.localdate()
    events = event_queryset_for_filter(
        request.user,
        summary.filter_name,
        today=today,
    )
    total = events.count()
    summary_events = list(events[:MODAL_EVENT_LIMIT])
    items = [
        event_read_item(event, filter_name=summary.filter_name)
        for event in summary_events
    ]
    fallback_url = event_list_url(summary.filter_name)

    context = {
        "modal_config": {
            "eyebrow": "Vista rápida",
            "title": summary.title,
            "description": summary.description,
            "icon": summary.icon,
            "empty_message": summary.empty_message,
            "footer_note": None,
        },
        "elementos": items,
        "cantidad_total": total,
        "cantidad_oculta": max(total - MODAL_EVENT_LIMIT, 0),
        "acciones": (
            {"url": fallback_url, "label": "Abrir Eventos"},
        ),
    }
    return modal_content_response(
        request,
        template_name="agenda/modales/listado_lectura.html",
        context=context,
        fallback_url=fallback_url,
    )


@login_required
@require_GET
def evento_pasado_pendiente(request):
    """
    Devuelve el evento más reciente que terminó durante
    las últimas 24 horas y todavía conserva estado programado.
    """

    now = timezone.now()
    notice_start = now - timedelta(hours=24)

    event = (
        Evento.objects
        .filter(
            usuario=request.user,
            estado=Evento.Estado.PROGRAMADO,
            fin__gte=notice_start,
            fin__lte=now,
        )
        .order_by("-fin", "-id")
        .first()
    )

    if event is None:
        payload = {
            "ok": True,
            "event": None,
        }
    else:
        local_end = timezone.localtime(event.fin)
        payload = {
            "ok": True,
            "event": {
                "id": event.id,
                "tag": (
                    f"bfgenda-past-event-{event.id}-"
                    f"{local_end:%Y%m%d%H%M}"
                ),
                "modal_url": reverse(
                    "agenda:evento_pasado_aviso",
                    args=[event.id],
                ),
            },
        }

    response = JsonResponse(payload)
    response["Cache-Control"] = "no-store"
    return response


@login_required
@require_GET
def evento_pasado_aviso(request, evento_id):
    """Muestra las opciones para un evento que ya terminó."""

    event = get_object_or_404(
        Evento,
        id=evento_id,
        usuario=request.user,
        estado=Evento.Estado.PROGRAMADO,
        fin__lte=timezone.now(),
    )

    return_url = event_list_url("pasados", event.id)
    local_start = timezone.localtime(event.inicio)
    local_end = timezone.localtime(event.fin)

    context = {
        "evento": event,
        "return_url": return_url,
        "inicio_local": local_start,
        "fin_local": local_end,
    }

    return modal_content_response(
        request,
        template_name="agenda/modales/evento_pasado.html",
        context=context,
        fallback_url=return_url,
    )


@login_required
def evento_crear(request):
    """Crea un evento normal o una serie semanal o mensual."""

    reference_date = parse_day(
        request.POST.get("fecha_referencia")
        if request.method == "POST"
        else request.GET.get("fecha"),
        None,
    )
    repeat_mode = _repeat_mode(request)
    fallback = (
        calendar_url_for_date(reference_date)
        if reference_date
        else reverse("agenda:eventos_listado")
    )
    return_url = get_return_url(request, fallback)
    hidden_fields = [{"name": "return_url", "value": return_url}]

    if reference_date:
        hidden_fields.append(
            {"name": "fecha_referencia", "value": reference_date.isoformat()}
        )
    if repeat_mode:
        hidden_fields.append({"name": "repetir", "value": repeat_mode})

    form_kwargs = {
        "usuario": request.user,
        "modo_repeticion": repeat_mode,
        "fecha_referencia": reference_date,
    }

    if request.method == "POST":
        form = EventoForm(request.POST, **form_kwargs)

        if form.is_valid():
            if repeat_mode:
                created_count = create_recurring_events(
                    user=request.user,
                    cleaned_data=form.cleaned_data,
                    repeat_mode=repeat_mode,
                )
                event_date = form.cleaned_data["inicio"].date()
                message = (
                    f"Se crearon {created_count} eventos "
                    f"{repeat_mode_plural(repeat_mode)}."
                )
            else:
                event = form.save(commit=False)
                event.usuario = request.user
                event.save()
                event_date = timezone.localtime(event.inicio).date()
                message = "El evento se creó correctamente."

            return saved_response(
                request,
                message=message,
                redirect_url=return_url,
                date_value=event_date,
                created=True,
            )

        return form_response(
            request,
            form,
            _event_form_config(
                editing=False,
                repeat_mode=repeat_mode,
                cancel_url=return_url,
                hidden_fields=hidden_fields,
            ),
            invalid=True,
        )

    preferences = get_user_preferences(request.user)
    initial_date = reference_date or timezone.localdate()
    current_tz = timezone.get_current_timezone()
    start = timezone.make_aware(
        datetime.combine(initial_date, preferences.hora_inicio_evento),
        current_tz,
    )
    initial = {
        "inicio": start,
        "fin": start + timedelta(
            minutes=preferences.duracion_evento_minutos
        ),
    }

    form = EventoForm(initial=initial, **form_kwargs)
    return form_response(
        request,
        form,
        _event_form_config(
            editing=False,
            repeat_mode=repeat_mode,
            cancel_url=return_url,
            hidden_fields=hidden_fields,
        ),
    )


@login_required
def evento_editar(request, evento_id):
    """Edita un evento únicamente desde el apartado Eventos."""

    event = get_object_or_404(Evento, id=evento_id, usuario=request.user)
    fallback = event_list_url("todos", event.id)
    return_url = get_return_url(request, fallback)
    hidden_fields = ({"name": "return_url", "value": return_url},)

    if request.method == "POST":
        form = EventoForm(request.POST, instance=event, usuario=request.user)

        if form.is_valid():
            event = form.save()
            event_date = timezone.localtime(event.inicio).date()
            return saved_response(
                request,
                message="El evento se actualizó correctamente.",
                redirect_url=return_url,
                date_value=event_date,
            )

        return form_response(
            request,
            form,
            _event_form_config(
                editing=True,
                repeat_mode=None,
                cancel_url=return_url,
                hidden_fields=hidden_fields,
            ),
            invalid=True,
        )

    form = EventoForm(instance=event, usuario=request.user)
    return form_response(
        request,
        form,
        _event_form_config(
            editing=True,
            repeat_mode=None,
            cancel_url=return_url,
            hidden_fields=hidden_fields,
        ),
    )


@login_required
@require_POST
def evento_cancelar(request, evento_id):
    """Cancela un evento sin eliminarlo del historial."""

    event = get_object_or_404(
        Evento,
        id=evento_id,
        usuario=request.user,
    )
    event.estado = Evento.Estado.CANCELADO
    event.save(update_fields=("estado", "actualizado_en"))

    return_url = get_return_url(
        request,
        event_list_url("cancelados", event.id),
    )
    return saved_response(
        request,
        message=f'El evento "{event.titulo}" fue cancelado.',
        redirect_url=return_url,
    )


@login_required
@require_POST
def evento_restaurar(request, evento_id):
    """Devuelve un evento cancelado a su estado normal."""

    event = get_object_or_404(
        Evento,
        id=evento_id,
        usuario=request.user,
    )
    event.estado = Evento.Estado.PROGRAMADO
    event.save(update_fields=("estado", "actualizado_en"))

    target_filter = (
        "pasados"
        if event.fin < timezone.now()
        else "proximos"
    )
    return_url = get_return_url(
        request,
        event_list_url(target_filter, event.id),
    )
    return saved_response(
        request,
        message=f'El evento "{event.titulo}" fue restaurado.',
        redirect_url=return_url,
    )


@login_required
@require_http_methods(["GET", "POST"])
def evento_eliminar(request, evento_id):
    """Elimina un evento únicamente después de una confirmación explícita."""

    event = get_object_or_404(Evento, id=evento_id, usuario=request.user)
    fallback = event_list_url("todos")
    return_url = get_return_url(request, fallback)

    if request.method == "POST":
        title = event.titulo
        event.delete()
        return saved_response(
            request,
            message=f'El evento "{title}" se eliminó correctamente.',
            redirect_url=return_url,
        )

    start_local = timezone.localtime(event.inicio)
    end_local = timezone.localtime(event.fin)
    schedule_detail = (
        f"Todo el día: {start_local:%d/%m/%Y}."
        if event.todo_el_dia
        else f"Horario: {start_local:%d/%m/%Y %H:%M} – {end_local:%d/%m/%Y %H:%M}."
    )
    config = ConfirmationViewConfig(
        eyebrow="Eliminar evento",
        title=f'¿Eliminar "{event.titulo}"?',
        description=(
            "El evento desaparecerá de Eventos, Calendario y de los resúmenes "
            "donde esté incluido."
        ),
        icon="!",
        confirm_label="Eliminar evento",
        cancel_url=return_url,
        action_url=reverse("agenda:evento_eliminar", args=[event.id]),
        details=(schedule_detail, f"Estado actual: {event.get_estado_display()}."),
        hidden_fields=({"name": "return_url", "value": return_url},),
    )
    return confirmation_response(request, config)


@login_required
@require_http_methods(["GET", "POST"])
def evento_serie_eliminar(request, evento_id):
    """Elimina todos los eventos que pertenecen a una serie recurrente."""

    event = get_object_or_404(
        Evento,
        id=evento_id,
        usuario=request.user,
        serie_recurrencia__isnull=False,
    )
    event_date = timezone.localtime(event.inicio).date()
    fallback = calendar_url_for_date(event_date)
    return_url = get_return_url(request, fallback)
    series = Evento.objects.filter(
        usuario=request.user,
        serie_recurrencia=event.serie_recurrencia,
    )
    occurrence_count = series.count()

    if request.method == "POST":
        title = event.titulo
        series.delete()
        return saved_response(
            request,
            message=(
                f'Se eliminó la serie "{title}" '
                f'con {occurrence_count} evento'
                f'{"s" if occurrence_count != 1 else ""}.'
            ),
            redirect_url=return_url,
        )

    recurrence_label = event.get_tipo_recurrencia_display().lower()
    config = ConfirmationViewConfig(
        eyebrow="Eliminar serie de eventos",
        title=f'¿Eliminar toda la serie "{event.titulo}"?',
        description=(
            "Se eliminarán todos los eventos de esta repetición, no solo la "
            "ocurrencia seleccionada."
        ),
        icon="!",
        confirm_label="Eliminar serie completa",
        cancel_url=return_url,
        action_url=reverse("agenda:evento_serie_eliminar", args=[event.id]),
        warning="Esta acción elimina la serie completa y no se puede deshacer.",
        details=(
            f"Repetición {recurrence_label}.",
            f"{occurrence_count} evento"
            f'{"s" if occurrence_count != 1 else ""} incluidos.',
        ),
        hidden_fields=({"name": "return_url", "value": return_url},),
    )
    return confirmation_response(request, config)
