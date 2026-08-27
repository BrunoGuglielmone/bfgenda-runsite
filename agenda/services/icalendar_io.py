"""Importación y exportación interoperable de calendarios iCalendar."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256

from django.db import transaction
from django.utils import timezone
from icalendar import Calendar, Event as ICalendarEvent

from agenda.models import Categoria, Evento
from agenda.services.exports import ExportFile


MAX_ICS_FILE_BYTES = 2 * 1024 * 1024
MAX_ICS_EVENTS = 500
ICAL_PRODUCT_ID = "-//BFGenda//Calendario personal//ES"
ICAL_FILENAME_PREFIX = "bfgenda-calendario"
RECURRENCE_PROPERTIES = (
    "rrule",
    "rdate",
    "exdate",
    "recurrence-id",
)


class CalendarImportError(ValueError):
    """Error legible producido al validar o interpretar un archivo .ics."""


@dataclass(frozen=True)
class CalendarImportResult:
    """Resumen de una importación de eventos."""

    total: int
    imported: int
    duplicates: int
    recurring_skipped: int
    invalid: int

    @property
    def message(self) -> str:
        parts = [
            (
                f"Se importó {self.imported} evento."
                if self.imported == 1
                else f"Se importaron {self.imported} eventos."
            )
        ]

        skipped = []
        if self.duplicates:
            skipped.append(
                f"{self.duplicates} duplicado"
                if self.duplicates == 1
                else f"{self.duplicates} duplicados"
            )
        if self.recurring_skipped:
            skipped.append(
                f"{self.recurring_skipped} recurrente"
                if self.recurring_skipped == 1
                else f"{self.recurring_skipped} recurrentes"
            )
        if self.invalid:
            skipped.append(
                f"{self.invalid} inválido"
                if self.invalid == 1
                else f"{self.invalid} inválidos"
            )

        if skipped:
            parts.append(f"Omitidos: {', '.join(skipped)}.")

        return " ".join(parts)


@dataclass(frozen=True)
class _ImportedEventData:
    """Datos normalizados antes de crear un Evento de Django."""

    title: str
    description: str
    start: datetime
    end: datetime
    all_day: bool
    location: str
    status: str
    uid: str | None



def _local_datetime(value: datetime) -> datetime:
    """Convierte un datetime a la zona activa y asume zona local si es ingenuo."""

    current_zone = timezone.get_current_timezone()

    if timezone.is_naive(value):
        value = timezone.make_aware(value, current_zone)

    return timezone.localtime(value, current_zone)



def _midnight(day_value: date) -> datetime:
    return timezone.make_aware(
        datetime.combine(day_value, time.min),
        timezone.get_current_timezone(),
    )



def _decoded(component, property_name: str):
    if component.get(property_name) is None:
        return None

    try:
        return component.decoded(property_name)
    except (KeyError, TypeError, ValueError):
        return None



def _clean_text(value, *, limit: int, required: bool = False) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\x00", "").strip()

    if required and not text:
        raise CalendarImportError("El evento no tiene título.")

    return text[:limit]



def _normalize_uid(value) -> str | None:
    if value is None:
        return None

    uid = str(value).replace("\x00", "").strip()
    if not uid:
        return None

    if len(uid) <= 255:
        return uid

    digest = sha256(uid.encode("utf-8", errors="replace")).hexdigest()
    return f"sha256:{digest}"



def _event_status(component) -> str:
    custom_status = str(component.get("x-bfgenda-status", "")).strip().lower()
    valid_statuses = {choice for choice, _label in Evento.Estado.choices}

    if custom_status in valid_statuses:
        return custom_status

    standard_status = str(component.get("status", "")).strip().upper()
    if standard_status == "CANCELLED":
        return Evento.Estado.CANCELADO

    return Evento.Estado.PROGRAMADO



def _event_dates(component) -> tuple[datetime, datetime, bool]:
    raw_start = _decoded(component, "dtstart")

    if raw_start is None:
        raise CalendarImportError("El evento no tiene fecha de inicio.")

    raw_end = _decoded(component, "dtend")
    duration = _decoded(component, "duration")

    if isinstance(raw_start, datetime):
        start = _local_datetime(raw_start)

        if raw_end is None:
            end = start + (
                duration if isinstance(duration, timedelta) else timedelta(hours=1)
            )
        elif isinstance(raw_end, datetime):
            end = _local_datetime(raw_end)
        else:
            raise CalendarImportError(
                "La finalización no utiliza el mismo tipo de fecha que el inicio."
            )

        if end <= start:
            raise CalendarImportError(
                "La finalización debe ser posterior al inicio."
            )

        return start, end, False

    if not isinstance(raw_start, date):
        raise CalendarImportError("La fecha de inicio no es válida.")

    start_day = raw_start

    if raw_end is None:
        if isinstance(duration, timedelta):
            end_day = start_day + duration
        else:
            end_day = start_day + timedelta(days=1)
    elif isinstance(raw_end, datetime):
        raise CalendarImportError(
            "La finalización no utiliza el mismo tipo de fecha que el inicio."
        )
    elif isinstance(raw_end, date):
        end_day = raw_end
    else:
        raise CalendarImportError("La fecha de finalización no es válida.")

    if end_day <= start_day:
        raise CalendarImportError(
            "La finalización debe ser posterior al inicio."
        )

    return _midnight(start_day), _midnight(end_day), True



def _component_to_event_data(component) -> _ImportedEventData:
    title = _clean_text(component.get("summary"), limit=180, required=True)
    description = _clean_text(component.get("description"), limit=10000)
    location = _clean_text(component.get("location"), limit=220)
    start, end, all_day = _event_dates(component)

    return _ImportedEventData(
        title=title,
        description=description,
        start=start,
        end=end,
        all_day=all_day,
        location=location,
        status=_event_status(component),
        uid=_normalize_uid(component.get("uid")),
    )



def _fingerprint(*, title: str, start: datetime, end: datetime, location: str):
    return (
        title.casefold().strip(),
        start.astimezone(UTC),
        end.astimezone(UTC),
        location.casefold().strip(),
    )



def _contains_recurrence(component) -> bool:
    return any(component.get(name) is not None for name in RECURRENCE_PROPERTIES)



def import_ics_events(user, uploaded_file, *, category: Categoria | None = None):
    """Importa VEVENT simples, omitiendo duplicados y reglas recurrentes."""

    if category is not None and category.usuario_id != user.id:
        raise CalendarImportError("La categoría seleccionada no pertenece al usuario.")

    content = uploaded_file.read()

    if not content:
        raise CalendarImportError("El archivo está vacío.")

    if len(content) > MAX_ICS_FILE_BYTES:
        raise CalendarImportError("El archivo supera el límite de 2 MB.")

    try:
        calendar = Calendar.from_ical(content)
    except (ValueError, TypeError, UnicodeError) as error:
        raise CalendarImportError(
            "No se pudo interpretar el archivo como un calendario iCalendar válido."
        ) from error

    components = list(calendar.walk("VEVENT"))

    if not components:
        raise CalendarImportError("El archivo no contiene eventos VEVENT.")

    if len(components) > MAX_ICS_EVENTS:
        raise CalendarImportError(
            f"El archivo contiene más de {MAX_ICS_EVENTS} eventos. "
            "Divide el calendario en archivos más pequeños."
        )

    existing_uids = set(
        Evento.objects.filter(
            usuario=user,
            ical_uid__isnull=False,
        ).values_list("ical_uid", flat=True)
    )
    existing_fingerprints = {
        _fingerprint(
            title=title,
            start=start,
            end=end,
            location=location,
        )
        for title, start, end, location in Evento.objects.filter(
            usuario=user
        ).values_list("titulo", "inicio", "fin", "ubicacion")
    }

    imported_objects = []
    duplicates = 0
    recurring_skipped = 0
    invalid = 0

    for component in components:
        if _contains_recurrence(component):
            recurring_skipped += 1
            continue

        try:
            data = _component_to_event_data(component)
        except CalendarImportError:
            invalid += 1
            continue

        fingerprint = _fingerprint(
            title=data.title,
            start=data.start,
            end=data.end,
            location=data.location,
        )

        if (
            (data.uid is not None and data.uid in existing_uids)
            or fingerprint in existing_fingerprints
        ):
            duplicates += 1
            continue

        imported_objects.append(
            Evento(
                usuario=user,
                categoria=category,
                titulo=data.title,
                descripcion=data.description,
                inicio=data.start,
                fin=data.end,
                todo_el_dia=data.all_day,
                ubicacion=data.location,
                estado=data.status,
                ical_uid=data.uid,
            )
        )

        existing_fingerprints.add(fingerprint)
        if data.uid is not None:
            existing_uids.add(data.uid)

    with transaction.atomic():
        for imported_event in imported_objects:
            imported_event.save()

    return CalendarImportResult(
        total=len(components),
        imported=len(imported_objects),
        duplicates=duplicates,
        recurring_skipped=recurring_skipped,
        invalid=invalid,
    )



def _event_uid(event: Evento) -> str:
    return event.ical_uid or f"bfgenda-event-{event.pk}@local"



def _all_day_export_range(event: Evento) -> tuple[date, date]:
    start_local = _local_datetime(event.inicio)
    end_local = _local_datetime(event.fin)
    start_day = start_local.date()

    if end_local.time() == time.min:
        end_day = end_local.date()
    else:
        end_day = end_local.date() + timedelta(days=1)

    if end_day <= start_day:
        end_day = start_day + timedelta(days=1)

    return start_day, end_day



def build_ics_export(user) -> ExportFile:
    """Genera un calendario .ics con todos los eventos del usuario."""

    now = timezone.now()
    calendar = Calendar()
    calendar.add("prodid", ICAL_PRODUCT_ID)
    calendar.add("version", "2.0")
    calendar.add("calscale", "GREGORIAN")
    calendar.add("method", "PUBLISH")
    calendar.add("x-wr-calname", "BFGenda")

    events = (
        Evento.objects.filter(usuario=user)
        .select_related("categoria")
        .order_by("inicio", "titulo")
    )

    for event in events:
        component = ICalendarEvent()
        component.add("uid", _event_uid(event))
        component.add("summary", event.titulo)
        component.add("dtstamp", now.astimezone(UTC))
        component.add("created", event.creado_en.astimezone(UTC))
        component.add("last-modified", event.actualizado_en.astimezone(UTC))

        if event.todo_el_dia:
            start_day, end_day = _all_day_export_range(event)
            component.add("dtstart", start_day)
            component.add("dtend", end_day)
        else:
            component.add("dtstart", event.inicio.astimezone(UTC))
            component.add("dtend", event.fin.astimezone(UTC))

        if event.descripcion:
            component.add("description", event.descripcion)
        if event.ubicacion:
            component.add("location", event.ubicacion)
        if event.categoria:
            component.add("categories", [event.categoria.nombre])

        if event.estado == Evento.Estado.CANCELADO:
            component.add("status", "CANCELLED")
        else:
            component.add("status", "CONFIRMED")

        component.add("x-bfgenda-status", event.estado)
        component.add("transp", "OPAQUE")
        calendar.add_component(component)

    local_now = timezone.localtime(now)
    content = calendar.to_ical()

    return ExportFile(
        content=content,
        filename=f"{ICAL_FILENAME_PREFIX}-{local_now:%Y%m%d-%H%M%S}.ics",
        content_type="text/calendar; charset=utf-8",
    )
