from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods

from agenda.forms import TareaForm
from agenda.models import Tarea
from agenda.services.preferences import get_user_preferences
from agenda.services.read_items import task_read_item
from agenda.services.recurrence import (
    REPEAT_MONTHLY,
    create_recurring_tasks,
    normalize_repeat_mode,
    repeat_mode_plural,
)
from agenda.services.retention import COMPLETED_TASK_RETENTION_MONTHS
from agenda.services.task_queries import (
    get_task_summary_config,
    normalize_task_filter,
    task_counts,
    task_list_url,
    task_queryset_for_filter,
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


MODAL_TASK_LIMIT = 40


def _repeat_mode(request):
    value = request.POST.get("repetir") or request.GET.get("repetir")
    return normalize_repeat_mode(value)


def _task_form_config(
    *,
    editing: bool,
    repeat_mode=None,
    cancel_url: str,
    hidden_fields=(),
):
    if editing:
        title = "Editar tarea"
        description = "Modifica la información, la fecha, la prioridad o la categoría."
        eyebrow = "Tarea"
        icon = "✓"
        submit_label = "Guardar cambios"
    elif repeat_mode == REPEAT_MONTHLY:
        title = "Nueva tarea mensual"
        description = (
            "Crea una tarea independiente para el mismo número de día de cada mes "
            "hasta la fecha que elijas."
        )
        eyebrow = "Tarea mensual"
        icon = "↻"
        submit_label = "Guardar tareas"
    elif repeat_mode:
        title = "Nueva tarea semanal"
        description = (
            "Crea una tarea independiente para el mismo día de cada semana "
            "hasta la fecha que elijas."
        )
        eyebrow = "Tarea semanal"
        icon = "↻"
        submit_label = "Guardar tareas"
    else:
        title = "Nueva tarea"
        description = "Registra algo que necesites realizar. La fecha es opcional."
        eyebrow = "Tarea"
        icon = "✓"
        submit_label = "Guardar tarea"

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
def tareas_listado(request):
    """Muestra las tareas del usuario y permite filtrarlas."""

    today = timezone.localdate()
    preferences = get_user_preferences(request.user)
    current_filter = normalize_task_filter(request.GET.get("filtro"))

    if current_filter == "sin_fecha_olvidadas":
        current_filter = "sin_fecha"

    tasks = task_queryset_for_filter(request.user, current_filter, today=today)
    counts = task_counts(
        request.user,
        today=today,
        reminder_days=preferences.dias_aviso_sin_fecha,
    )

    context = {
        "fecha_actual": today,
        "filtro_actual": current_filter,
        "tareas": tasks,
        "cantidad_resultados": tasks.count(),
        **counts,
    }
    return render(request, "agenda/tareas_listado.html", context)


@login_required
def tareas_resumen(request):
    """Entrega una lista rápida de solo lectura dentro del modal global."""

    preferences = get_user_preferences(request.user)
    summary = get_task_summary_config(
        request.GET.get("tipo"),
        reminder_days=preferences.dias_aviso_sin_fecha,
    )

    if summary is None:
        raise Http404("El resumen solicitado no existe.")

    today = timezone.localdate()
    tasks = task_queryset_for_filter(
        request.user,
        summary.filter_name,
        today=today,
        reminder_days=preferences.dias_aviso_sin_fecha,
    )
    total = tasks.count()
    summary_tasks = list(tasks[:MODAL_TASK_LIMIT])
    destination_filter = summary.list_filter_name or summary.filter_name
    items = [
        task_read_item(task, filter_name=destination_filter)
        for task in summary_tasks
    ]
    fallback_url = task_list_url(destination_filter)
    footer_note = None

    if summary.key == "completadas":
        footer_note = (
            f"El historial se conserva durante {COMPLETED_TASK_RETENTION_MONTHS} meses."
        )

    context = {
        "modal_config": {
            "eyebrow": "Vista rápida",
            "title": summary.title,
            "description": summary.description,
            "icon": summary.icon,
            "empty_message": summary.empty_message,
            "footer_note": footer_note,
        },
        "elementos": items,
        "cantidad_total": total,
        "cantidad_oculta": max(total - MODAL_TASK_LIMIT, 0),
        "acciones": (
            {"url": fallback_url, "label": "Abrir Tareas"},
        ),
    }
    return modal_content_response(
        request,
        template_name="agenda/modales/listado_lectura.html",
        context=context,
        fallback_url=fallback_url,
    )


@login_required
def tarea_crear(request):
    """Crea una tarea normal o una serie semanal o mensual."""

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
        else reverse("agenda:tareas_listado")
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
        form = TareaForm(request.POST, **form_kwargs)

        if form.is_valid():
            if repeat_mode:
                created_count = create_recurring_tasks(
                    user=request.user,
                    cleaned_data=form.cleaned_data,
                    repeat_mode=repeat_mode,
                )
                message = (
                    f"Se crearon {created_count} tareas "
                    f"{repeat_mode_plural(repeat_mode)}."
                )
                date_value = form.cleaned_data["fecha_limite"]
            else:
                task = form.save(commit=False)
                task.usuario = request.user
                task.save()
                message = "La tarea se creó correctamente."
                date_value = task.fecha_limite or reference_date

            return saved_response(
                request,
                message=message,
                redirect_url=return_url,
                date_value=date_value,
                created=True,
            )

        return form_response(
            request,
            form,
            _task_form_config(
                editing=False,
                repeat_mode=repeat_mode,
                cancel_url=return_url,
                hidden_fields=hidden_fields,
            ),
            invalid=True,
        )

    initial = {"fecha_limite": reference_date} if reference_date else {}
    form = TareaForm(initial=initial, **form_kwargs)
    return form_response(
        request,
        form,
        _task_form_config(
            editing=False,
            repeat_mode=repeat_mode,
            cancel_url=return_url,
            hidden_fields=hidden_fields,
        ),
    )


@login_required
def tarea_editar(request, tarea_id):
    """Edita una tarea perteneciente al usuario autenticado."""

    task = get_object_or_404(Tarea, id=tarea_id, usuario=request.user)
    return_url = get_return_url(request, reverse("agenda:tareas_listado"))
    hidden_fields = ({"name": "return_url", "value": return_url},)

    if request.method == "POST":
        form = TareaForm(request.POST, instance=task, usuario=request.user)

        if form.is_valid():
            task = form.save()
            return saved_response(
                request,
                message="La tarea se actualizó correctamente.",
                redirect_url=return_url,
                date_value=task.fecha_limite,
            )

        return form_response(
            request,
            form,
            _task_form_config(
                editing=True,
                repeat_mode=None,
                cancel_url=return_url,
                hidden_fields=hidden_fields,
            ),
            invalid=True,
        )

    form = TareaForm(instance=task, usuario=request.user)
    return form_response(
        request,
        form,
        _task_form_config(
            editing=True,
            repeat_mode=None,
            cancel_url=return_url,
            hidden_fields=hidden_fields,
        ),
    )


@login_required
@require_POST
def tarea_completar(request, tarea_id):
    task = get_object_or_404(Tarea, id=tarea_id, usuario=request.user)
    task.estado = Tarea.Estado.COMPLETADA
    task.completada_en = timezone.now()
    task.save(update_fields=["estado", "completada_en", "actualizada_en"])

    fallback = (
        reverse("agenda:tareas_listado")
        if request.POST.get("destino") == "tareas"
        else reverse("agenda:inicio")
    )
    return_url = get_return_url(request, fallback)
    return saved_response(
        request,
        message="La tarea se marcó como completada.",
        redirect_url=return_url,
    )


@login_required
@require_POST
def tarea_restaurar(request, tarea_id):
    task = get_object_or_404(
        Tarea,
        id=tarea_id,
        usuario=request.user,
        estado=Tarea.Estado.COMPLETADA,
    )
    task.estado = Tarea.Estado.PENDIENTE
    task.completada_en = None
    task.save(update_fields=["estado", "completada_en", "actualizada_en"])

    return_url = get_return_url(request, reverse("agenda:tareas_listado"))
    return saved_response(
        request,
        message="La tarea volvió al estado pendiente.",
        redirect_url=return_url,
    )


@login_required
@require_http_methods(["GET", "POST"])
def tarea_eliminar(request, tarea_id):
    """Elimina una tarea únicamente después de una confirmación explícita."""

    task = get_object_or_404(Tarea, id=tarea_id, usuario=request.user)
    fallback = task_list_url("todas")
    return_url = get_return_url(request, fallback)

    if request.method == "POST":
        title = task.titulo
        task.delete()
        return saved_response(
            request,
            message=f'La tarea "{title}" se eliminó correctamente.',
            redirect_url=return_url,
        )

    date_detail = (
        f"Fecha límite: {task.fecha_limite:%d/%m/%Y}."
        if task.fecha_limite
        else "La tarea no tiene fecha límite."
    )
    config = ConfirmationViewConfig(
        eyebrow="Eliminar tarea",
        title=f'¿Eliminar "{task.titulo}"?',
        description=(
            "La tarea desaparecerá de Tareas, Calendario y de los resúmenes "
            "donde esté incluida."
        ),
        icon="!",
        confirm_label="Eliminar tarea",
        cancel_url=return_url,
        action_url=reverse("agenda:tarea_eliminar", args=[task.id]),
        details=(date_detail, f"Estado actual: {task.get_estado_display()}."),
        hidden_fields=({"name": "return_url", "value": return_url},),
    )
    return confirmation_response(request, config)


@login_required
@require_http_methods(["GET", "POST"])
def tarea_serie_eliminar(request, tarea_id):
    """Elimina todas las tareas que pertenecen a una serie recurrente."""

    task = get_object_or_404(
        Tarea,
        id=tarea_id,
        usuario=request.user,
        serie_recurrencia__isnull=False,
    )
    fallback = calendar_url_for_date(task.fecha_limite)
    return_url = get_return_url(request, fallback)
    series = Tarea.objects.filter(
        usuario=request.user,
        serie_recurrencia=task.serie_recurrencia,
    )
    occurrence_count = series.count()

    if request.method == "POST":
        title = task.titulo
        series.delete()
        return saved_response(
            request,
            message=(
                f'Se eliminó la serie "{title}" '
                f'con {occurrence_count} tarea'
                f'{"s" if occurrence_count != 1 else ""}.'
            ),
            redirect_url=return_url,
        )

    recurrence_label = task.get_tipo_recurrencia_display().lower()
    config = ConfirmationViewConfig(
        eyebrow="Eliminar serie de tareas",
        title=f'¿Eliminar toda la serie "{task.titulo}"?',
        description=(
            "Se eliminarán todas las tareas de esta repetición, no solo la "
            "ocurrencia seleccionada."
        ),
        icon="!",
        confirm_label="Eliminar serie completa",
        cancel_url=return_url,
        action_url=reverse("agenda:tarea_serie_eliminar", args=[task.id]),
        warning="Esta acción elimina la serie completa y no se puede deshacer.",
        details=(
            f"Repetición {recurrence_label}.",
            f"{occurrence_count} tarea"
            f'{"s" if occurrence_count != 1 else ""} incluidas.',
        ),
        hidden_fields=({"name": "return_url", "value": return_url},),
    )
    return confirmation_response(request, config)
