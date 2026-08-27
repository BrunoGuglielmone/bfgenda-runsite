from datetime import UTC, datetime, timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from icalendar import Calendar

from agenda.models import Categoria, Evento
from agenda.services.icalendar_io import (
    build_ics_export,
    import_ics_events,
)


AJAX_HEADERS = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


def _ics_file(content: str, name: str = "calendario.ics"):
    return SimpleUploadedFile(
        name,
        content.encode("utf-8"),
        content_type="text/calendar",
    )


class ICalendarServiceTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="bruno-ics",
            password="clave-segura",
        )
        self.other_user = user_model.objects.create_user(
            username="otra-persona-ics",
            password="otra-clave",
        )
        self.category = Categoria.objects.create(
            usuario=self.user,
            nombre="Estudio",
            color="#6657D9",
        )

    def test_export_contains_only_authenticated_users_events(self):
        start = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
        own_event = Evento.objects.create(
            usuario=self.user,
            categoria=self.category,
            titulo="Evento exportado",
            descripcion="Descripción de prueba",
            inicio=start,
            fin=start + timedelta(hours=1),
            ubicacion="CeRP",
        )
        Evento.objects.create(
            usuario=self.other_user,
            titulo="Evento privado ajeno",
            inicio=start,
            fin=start + timedelta(hours=2),
        )

        exported = build_ics_export(self.user)
        calendar = Calendar.from_ical(exported.content)
        events = list(calendar.walk("VEVENT"))

        self.assertEqual(len(events), 1)
        self.assertEqual(str(events[0].get("summary")), own_event.titulo)
        self.assertEqual(str(events[0].get("location")), "CeRP")
        self.assertEqual(
            str(events[0].get("uid")),
            f"bfgenda-event-{own_event.id}@local",
        )
        self.assertTrue(exported.filename.endswith(".ics"))

    def test_import_creates_timed_and_all_day_events(self):
        content = """BEGIN:VCALENDAR\r
VERSION:2.0\r
PRODID:-//Prueba//ES\r
BEGIN:VEVENT\r
UID:reunion-1@example.test\r
DTSTART:20260810T120000Z\r
DTEND:20260810T130000Z\r
SUMMARY:Reunión importada\r
LOCATION:Videollamada\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:jornada-1@example.test\r
DTSTART;VALUE=DATE:20260812\r
DTEND;VALUE=DATE:20260813\r
SUMMARY:Jornada completa\r
END:VEVENT\r
END:VCALENDAR\r
"""

        result = import_ics_events(
            self.user,
            _ics_file(content),
            category=self.category,
        )

        self.assertEqual(result.imported, 2)
        self.assertEqual(result.duplicates, 0)
        meeting = Evento.objects.get(ical_uid="reunion-1@example.test")
        all_day = Evento.objects.get(ical_uid="jornada-1@example.test")
        self.assertEqual(meeting.categoria, self.category)
        self.assertFalse(meeting.todo_el_dia)
        self.assertTrue(timezone.is_aware(meeting.inicio))
        self.assertTrue(all_day.todo_el_dia)
        self.assertGreater(all_day.fin, all_day.inicio)

    def test_import_skips_duplicates_and_recurrence_rules(self):
        content = """BEGIN:VCALENDAR\r
VERSION:2.0\r
PRODID:-//Prueba//ES\r
BEGIN:VEVENT\r
UID:evento-unico@example.test\r
DTSTART:20260810T120000Z\r
DTEND:20260810T130000Z\r
SUMMARY:Evento único\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:evento-recurrente@example.test\r
DTSTART:20260811T120000Z\r
DTEND:20260811T130000Z\r
RRULE:FREQ=WEEKLY;COUNT=3\r
SUMMARY:Evento recurrente\r
END:VEVENT\r
END:VCALENDAR\r
"""

        first_result = import_ics_events(self.user, _ics_file(content))
        second_result = import_ics_events(self.user, _ics_file(content))

        self.assertEqual(first_result.imported, 1)
        self.assertEqual(first_result.recurring_skipped, 1)
        self.assertEqual(second_result.imported, 0)
        self.assertEqual(second_result.duplicates, 1)
        self.assertEqual(second_result.recurring_skipped, 1)
        self.assertEqual(
            Evento.objects.filter(usuario=self.user).count(),
            1,
        )


class ICalendarViewsTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="bruno-view-ics",
            password="clave-segura",
        )
        self.client.force_login(self.user)

    def test_import_modal_is_multipart(self):
        response = self.client.get(
            reverse("agenda:importar_ics"),
            **AJAX_HEADERS,
        )

        self.assertEqual(response.status_code, 200)
        html = response.json()["html"]
        self.assertIn('enctype="multipart/form-data"', html)
        self.assertIn("Importar eventos", html)

    def test_ajax_import_returns_result_and_creates_event(self):
        content = """BEGIN:VCALENDAR\r
VERSION:2.0\r
PRODID:-//Prueba//ES\r
BEGIN:VEVENT\r
UID:vista-1@example.test\r
DTSTART:20260810T120000Z\r
DTEND:20260810T130000Z\r
SUMMARY:Importado desde la vista\r
END:VEVENT\r
END:VCALENDAR\r
"""

        response = self.client.post(
            reverse("agenda:importar_ics"),
            {
                "archivo": _ics_file(content),
                "categoria": "",
                "return_url": reverse("agenda:configuracion"),
            },
            **AJAX_HEADERS,
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["ok"])
        self.assertIn("Se importó 1 evento", response.json()["message"])
        self.assertTrue(
            Evento.objects.filter(
                usuario=self.user,
                titulo="Importado desde la vista",
            ).exists()
        )

    def test_ics_export_view_downloads_calendar(self):
        start = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
        Evento.objects.create(
            usuario=self.user,
            titulo="Evento descargable",
            inicio=start,
            fin=start + timedelta(hours=1),
        )

        response = self.client.get(reverse("agenda:exportar_ics"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/calendar; charset=utf-8")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(".ics", response["Content-Disposition"])
        self.assertIn(b"BEGIN:VCALENDAR", response.content)
        self.assertIn("Evento descargable".encode("utf-8"), response.content)
