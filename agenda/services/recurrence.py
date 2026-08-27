from calendar import monthrange
from datetime import date, timedelta
from uuid import uuid4

from django.db import transaction

from agenda.models import Evento, Tarea


REPEAT_WEEKLY = "semanal"
REPEAT_MONTHLY = "mensual"
REPEAT_MODES = frozenset({REPEAT_WEEKLY, REPEAT_MONTHLY})
MAX_REPEAT_DAYS = 366
MAX_WEEKLY_OCCURRENCES = 53
MAX_MONTHS_CHECKED = 13


def normalize_repeat_mode(value):
    """Devuelve un modo de repetición admitido o ``None``."""

    return value if value in REPEAT_MODES else None


def repeat_mode_plural(value):
    """Adjetivo plural utilizado en los mensajes de confirmación."""

    return {
        REPEAT_WEEKLY: "semanales",
        REPEAT_MONTHLY: "mensuales",
    }.get(value, "")


def weekly_dates(start_date, end_date):
    """Genera fechas semanales inclusivas con un límite de seguridad anual."""

    current = start_date
    count = 0

    while current <= end_date and count < MAX_WEEKLY_OCCURRENCES:
        yield current
        current += timedelta(days=7)
        count += 1


def monthly_dates(start_date, end_date):
    """
    Genera el mismo número de día en cada mes.

    Los meses que no contienen ese número se omiten. Por ejemplo, una serie
    iniciada un día 31 no crea ocurrencias en febrero, abril, junio, septiembre
    ni noviembre.
    """

    target_day = start_date.day
    year = start_date.year
    month = start_date.month
    months_checked = 0

    while months_checked < MAX_MONTHS_CHECKED:
        _, days_in_month = monthrange(year, month)

        if target_day <= days_in_month:
            occurrence = date(year, month, target_day)

            if occurrence > end_date:
                break

            if occurrence >= start_date:
                yield occurrence

        if month == 12:
            year += 1
            month = 1
        else:
            month += 1

        months_checked += 1


def recurrence_dates(start_date, end_date, repeat_mode):
    """Selecciona el generador adecuado para la repetición solicitada."""

    repeat_mode = normalize_repeat_mode(repeat_mode)

    if repeat_mode == REPEAT_WEEKLY:
        yield from weekly_dates(start_date, end_date)
    elif repeat_mode == REPEAT_MONTHLY:
        yield from monthly_dates(start_date, end_date)


@transaction.atomic
def create_recurring_tasks(*, user, cleaned_data, repeat_mode) -> int:
    """Crea tareas vinculadas a una misma serie recurrente."""

    start_date = cleaned_data["fecha_limite"]
    end_date = cleaned_data["repetir_hasta"]
    repeat_mode = normalize_repeat_mode(repeat_mode)
    series_id = uuid4()
    created = 0

    for occurrence_date in recurrence_dates(start_date, end_date, repeat_mode):
        Tarea.objects.create(
            usuario=user,
            categoria=cleaned_data.get("categoria"),
            titulo=cleaned_data["titulo"],
            descripcion=cleaned_data.get("descripcion", ""),
            fecha_limite=occurrence_date,
            hora_limite=cleaned_data.get("hora_limite"),
            prioridad=cleaned_data["prioridad"],
            serie_recurrencia=series_id,
            tipo_recurrencia=repeat_mode,
        )
        created += 1

    return created


@transaction.atomic
def create_recurring_events(*, user, cleaned_data, repeat_mode) -> int:
    """Crea eventos vinculados a una misma serie recurrente."""

    first_start = cleaned_data["inicio"]
    first_end = cleaned_data["fin"]
    end_date = cleaned_data["repetir_hasta"]
    repeat_mode = normalize_repeat_mode(repeat_mode)
    series_id = uuid4()
    duration = first_end - first_start
    created = 0

    for occurrence_date in recurrence_dates(
        first_start.date(),
        end_date,
        repeat_mode,
    ):
        offset = occurrence_date - first_start.date()
        occurrence_start = first_start + offset

        Evento.objects.create(
            usuario=user,
            categoria=cleaned_data.get("categoria"),
            titulo=cleaned_data["titulo"],
            descripcion=cleaned_data.get("descripcion", ""),
            inicio=occurrence_start,
            fin=occurrence_start + duration,
            todo_el_dia=cleaned_data.get("todo_el_dia", False),
            ubicacion=cleaned_data.get("ubicacion", ""),
            estado=Evento.Estado.PROGRAMADO,
            serie_recurrencia=series_id,
            tipo_recurrencia=repeat_mode,
        )
        created += 1

    return created
