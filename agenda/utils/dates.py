from calendar import monthrange
from datetime import date, datetime
from urllib.parse import urlencode

from django.urls import reverse


VALID_CALENDAR_VIEWS = {"dia", "semana", "mes"}


def parse_month(value: str | None, today: date) -> date:
    """Interpreta YYYY-MM o devuelve el primer día del mes actual."""

    if not value:
        return today.replace(day=1)

    try:
        return datetime.strptime(value, "%Y-%m").date().replace(day=1)
    except ValueError:
        return today.replace(day=1)


def parse_day(value: str | None, default: date | None) -> date | None:
    """Interpreta YYYY-MM-DD o devuelve la fecha predeterminada."""

    if not value:
        return default

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return default


def shift_months(value, amount: int):
    """Desplaza fechas o datetimes por meses conservando un día válido."""

    month_index = value.year * 12 + value.month - 1 + amount
    year = month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def add_months(base_date: date, amount: int) -> date:
    """Avanza o retrocede meses usando siempre el primer día."""

    return shift_months(base_date.replace(day=1), amount)


def normalize_calendar_view(value: str | None) -> str:
    """Normaliza la vista de calendario solicitada."""

    return value if value in VALID_CALENDAR_VIEWS else "mes"


def calendar_url_for_view(view: str, value: date) -> str:
    """Construye una URL de calendario para día, semana o mes."""

    normalized_view = normalize_calendar_view(view)
    params = {
        "vista": normalized_view,
        "dia": value.isoformat(),
    }

    if normalized_view == "mes":
        params["mes"] = value.strftime("%Y-%m")

    return f"{reverse('agenda:calendario')}?{urlencode(params)}"


def calendar_url_for_date(value: date) -> str:
    """Mantiene compatibilidad: abre una fecha en la vista mensual."""

    return calendar_url_for_view("mes", value)
