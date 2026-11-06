from django.utils import timezone

from agenda.services.event_queries import event_list_url
from agenda.services.task_queries import task_list_url


def task_read_item(task, *, filter_name="pendientes"):
    date_text = task.fecha_limite.strftime("%d/%m/%Y") if task.fecha_limite else "Sin fecha"
    time_text = task.hora_limite.strftime("%H:%M") if task.hora_limite else None
    category = task.categoria.nombre if task.categoria else "Sin categoría"
    category_color = task.categoria.color if task.categoria else "#9A9EAD"
    meta = " · ".join(
        value
        for value in (
            date_text,
            time_text,
            task.get_prioridad_display(),
        )
        if value
    )
    secondary = None

    if task.completada_en:
        secondary = f"Realizada el {timezone.localtime(task.completada_en):%d/%m/%Y %H:%M}"

    return {
        "titulo": task.titulo,
        "meta": meta,
        "secundario": secondary,
        "color": category_color,
        "categoria": category,
        "categoria_color": category_color,
        "tipo": "Tarea",
        "tipo_clase": "tarea",
        "url": task_list_url(filter_name, task.id),
        "destino": "Ver en Tareas →",
        "completado": task.estado == task.Estado.COMPLETADA,
    }


def event_read_item(event, *, filter_name="todos"):
    start = timezone.localtime(event.inicio)
    end = timezone.localtime(event.fin)
    date_text = (
        f"{start:%d/%m/%Y} · Todo el día"
        if event.todo_el_dia
        else f"{start:%d/%m/%Y %H:%M} – {end:%d/%m/%Y %H:%M}"
    )
    category = event.categoria.nombre if event.categoria else "Sin categoría"
    category_color = event.categoria.color if event.categoria else "#9A9EAD"
    meta = " · ".join(
        value
        for value in (
            date_text,
            event.ubicacion or None,
            event.get_estado_display(),
        )
        if value
    )

    return {
        "titulo": event.titulo,
        "meta": meta,
        "secundario": event.descripcion or None,
        "color": category_color,
        "categoria": category,
        "categoria_color": category_color,
        "tipo": "Evento",
        "tipo_clase": "evento",
        "url": event_list_url(filter_name, event.id),
        "destino": "Ver en Eventos →",
        "completado": event.estado == event.Estado.REALIZADO,
    }
