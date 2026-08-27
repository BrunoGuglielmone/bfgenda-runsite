from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.urls import reverse
from django.utils import timezone
from django.utils.text import Truncator

from agenda.models import Categoria, Evento, Tarea

from .event_queries import event_list_url
from .task_queries import task_list_url


MIN_SEARCH_LENGTH = 2
MODAL_RESULTS_PER_GROUP = 8
PAGE_RESULTS_PER_GROUP = 24
MAX_SEARCH_LENGTH = 120

SEARCH_TYPES = {
    "todo",
    "tareas",
    "eventos",
    "categorias",
}

SEARCH_TYPE_OPTIONS = (
    ("todo", "Todo"),
    ("tareas", "Tareas"),
    ("eventos", "Eventos"),
    ("categorias", "Categorías"),
)


@dataclass(frozen=True)
class SearchGroup:
    """Grupo de resultados presentado en la búsqueda global."""

    key: str
    title: str
    icon: str
    total: int
    items: tuple[dict[str, Any], ...]

    @property
    def hidden_count(self) -> int:
        return max(self.total - len(self.items), 0)


def normalize_search_query(value: str | None) -> str:
    """Limpia espacios y limita el tamaño de la consulta."""

    return " ".join((value or "").split())[:MAX_SEARCH_LENGTH]


def normalize_search_type(value: str | None) -> str:
    """Devuelve un tipo de búsqueda conocido."""

    return value if value in SEARCH_TYPES else "todo"


def _database_term(value: str) -> str:
    """Adapta expresiones visibles a valores internos con guion bajo."""

    return value.casefold().replace(" ", "_")


def _terms_condition(fields: tuple[str, ...], query: str) -> Q:
    """Exige que cada palabra aparezca en alguno de los campos indicados."""

    condition = Q()

    for term in query.split():
        term_condition = Q()

        for field in fields:
            term_condition |= Q(**{f"{field}__icontains": term})

        condition &= term_condition

    return condition


def _ranking_for_title(query: str):
    """Prioriza coincidencias exactas y títulos que comienzan por la consulta."""

    return Case(
        When(titulo__iexact=query, then=Value(0)),
        When(titulo__istartswith=query, then=Value(1)),
        default=Value(2),
        output_field=IntegerField(),
    )


def _ranking_for_name(query: str):
    return Case(
        When(nombre__iexact=query, then=Value(0)),
        When(nombre__istartswith=query, then=Value(1)),
        default=Value(2),
        output_field=IntegerField(),
    )


def _task_special_condition(query: str, today: date) -> Q:
    normalized = query.casefold()

    if normalized in {"vencida", "vencidas", "atrasada", "atrasadas"}:
        return Q(
            fecha_limite__lt=today,
        ) & ~Q(estado=Tarea.Estado.COMPLETADA)

    if normalized in {"sin fecha", "sin fechas"}:
        return Q(fecha_limite__isnull=True) & ~Q(
            estado=Tarea.Estado.COMPLETADA
        )

    if normalized in {"hoy", "para hoy"}:
        return Q(fecha_limite=today) & ~Q(estado=Tarea.Estado.COMPLETADA)

    return Q(pk__in=[])


def _event_special_condition(query: str, today: date) -> Q:
    normalized = query.casefold()

    if normalized not in {"hoy", "eventos de hoy"}:
        return Q(pk__in=[])

    start = timezone.make_aware(
        datetime.combine(today, time.min),
        timezone.get_current_timezone(),
    )
    end = start + timedelta(days=1)
    return Q(inicio__lt=end, fin__gt=start)


def _task_destination_filter(task: Tarea, today: date) -> str:
    if task.estado == Tarea.Estado.COMPLETADA:
        return "completadas"

    if task.fecha_limite is None:
        return "sin_fecha"

    if task.fecha_limite < today:
        return "vencidas"

    if task.fecha_limite == today:
        return "hoy"

    return "proximas"


def _event_destination_filter(event: Evento) -> str:
    if event.estado == Evento.Estado.REALIZADO:
        return "realizados"

    if event.estado == Evento.Estado.CANCELADO:
        return "cancelados"

    return "programados"


def _task_item(task: Tarea, today: date) -> dict[str, Any]:
    if task.fecha_limite is None:
        date_label = "Sin fecha"
    elif task.fecha_limite == today:
        date_label = "Hoy"
    elif task.fecha_limite < today and task.estado != Tarea.Estado.COMPLETADA:
        date_label = f"Vencida · {task.fecha_limite:%d/%m/%Y}"
    else:
        date_label = task.fecha_limite.strftime("%d/%m/%Y")

    metadata = [
        task.get_estado_display(),
        date_label,
        task.get_prioridad_display(),
        task.categoria.nombre if task.categoria else "Sin categoría",
    ]

    return {
        "kind": "tarea",
        "type_label": "Tarea",
        "icon": "✓",
        "title": task.titulo,
        "description": Truncator(task.descripcion).chars(125) if task.descripcion else "",
        "metadata": metadata,
        "color": task.categoria.color if task.categoria else "#9A9EAD",
        "url": task_list_url(
            _task_destination_filter(task, today),
            task.id,
        ),
    }


def _event_item(event: Evento) -> dict[str, Any]:
    start = timezone.localtime(event.inicio)
    end = timezone.localtime(event.fin)

    if event.todo_el_dia:
        date_label = f"{start:%d/%m/%Y} · Todo el día"
    elif start.date() == end.date():
        date_label = f"{start:%d/%m/%Y} · {start:%H:%M}–{end:%H:%M}"
    else:
        date_label = f"{start:%d/%m %H:%M} – {end:%d/%m %H:%M}"

    metadata = [
        event.get_estado_display(),
        date_label,
        event.categoria.nombre if event.categoria else "Sin categoría",
    ]

    if event.ubicacion:
        metadata.append(event.ubicacion)

    return {
        "kind": "evento",
        "type_label": "Evento",
        "icon": "◷",
        "title": event.titulo,
        "description": Truncator(event.descripcion).chars(125) if event.descripcion else "",
        "metadata": metadata,
        "color": event.categoria.color if event.categoria else "#9A9EAD",
        "url": event_list_url(
            _event_destination_filter(event),
            event.id,
        ),
    }


def _category_item(category: Categoria) -> dict[str, Any]:
    task_count = category.cantidad_tareas
    event_count = category.cantidad_eventos
    status = "Activa" if category.activa else "Inactiva"

    return {
        "kind": "categoria",
        "type_label": "Categoría",
        "icon": "●",
        "title": category.nombre,
        "description": "Organiza tareas y eventos mediante este color.",
        "metadata": [
            status,
            f"{task_count} tarea{'s' if task_count != 1 else ''}",
            f"{event_count} evento{'s' if event_count != 1 else ''}",
        ],
        "color": category.color,
        "url": reverse(
            "agenda:categorias_listado",
            fragment=f"categoria-{category.id}",
        ),
    }


def _search_tasks(user, query: str, limit: int, today: date) -> SearchGroup:
    text_condition = _terms_condition(
        (
            "titulo",
            "descripcion",
            "categoria__nombre",
        ),
        query,
    )
    database_term = _database_term(query)
    condition = (
        text_condition
        | Q(estado__icontains=database_term)
        | Q(prioridad__icontains=database_term)
        | _task_special_condition(query, today)
    )

    queryset = (
        Tarea.objects.filter(usuario=user)
        .select_related("categoria")
        .filter(condition)
        .annotate(search_rank=_ranking_for_title(query))
        .order_by("search_rank", "fecha_limite", "hora_limite", "titulo")
        .distinct()
    )
    total = queryset.count()
    items = tuple(_task_item(task, today) for task in queryset[:limit])
    return SearchGroup("tareas", "Tareas", "✓", total, items)


def _search_events(user, query: str, limit: int, today: date) -> SearchGroup:
    text_condition = _terms_condition(
        (
            "titulo",
            "descripcion",
            "ubicacion",
            "categoria__nombre",
        ),
        query,
    )
    database_term = _database_term(query)
    condition = (
        text_condition
        | Q(estado__icontains=database_term)
        | _event_special_condition(query, today)
    )

    queryset = (
        Evento.objects.filter(usuario=user)
        .select_related("categoria")
        .filter(condition)
        .annotate(search_rank=_ranking_for_title(query))
        .order_by("search_rank", "inicio", "titulo")
        .distinct()
    )
    total = queryset.count()
    items = tuple(_event_item(event) for event in queryset[:limit])
    return SearchGroup("eventos", "Eventos", "◷", total, items)


def _search_categories(user, query: str, limit: int) -> SearchGroup:
    queryset = (
        Categoria.objects.filter(
            usuario=user,
            nombre__icontains=query,
        )
        .annotate(
            cantidad_tareas=Count("tareas", distinct=True),
            cantidad_eventos=Count("eventos", distinct=True),
            search_rank=_ranking_for_name(query),
        )
        .order_by("search_rank", "nombre")
    )
    total = queryset.count()
    items = tuple(_category_item(category) for category in queryset[:limit])
    return SearchGroup("categorias", "Categorías", "●", total, items)


def global_search(
    user,
    query: str | None,
    *,
    search_type: str | None = "todo",
    limit: int = MODAL_RESULTS_PER_GROUP,
) -> dict[str, Any]:
    """Busca elementos del usuario y devuelve grupos listos para plantillas."""

    normalized_query = normalize_search_query(query)
    normalized_type = normalize_search_type(search_type)
    valid_query = len(normalized_query) >= MIN_SEARCH_LENGTH
    groups: list[SearchGroup] = []

    if valid_query:
        today = timezone.localdate()

        if normalized_type in {"todo", "tareas"}:
            groups.append(_search_tasks(user, normalized_query, limit, today))

        if normalized_type in {"todo", "eventos"}:
            groups.append(_search_events(user, normalized_query, limit, today))

        if normalized_type in {"todo", "categorias"}:
            groups.append(_search_categories(user, normalized_query, limit))

    visible_groups = tuple(group for group in groups if group.total > 0)
    total_results = sum(group.total for group in groups)

    return {
        "consulta": normalized_query,
        "tipo_busqueda": normalized_type,
        "tipos_busqueda": SEARCH_TYPE_OPTIONS,
        "consulta_valida": valid_query,
        "minimo_caracteres": MIN_SEARCH_LENGTH,
        "grupos": visible_groups,
        "total_resultados": total_results,
    }
