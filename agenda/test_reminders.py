"""Pruebas del endpoint de recordatorios autom?ticos."""

from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from agenda.models import Evento, PreferenciasUsuario, Tarea
from agenda.services.notifications import collect_due_reminders


def aware_local(year, month, day, hour, minute=0):
    zone = timezone.get_current_timezone()
    return timezone.make_aware(
        datetime(year, month, day, hour, minute),
        zone,
    )


class ReminderServiceTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="recordatorios",
            password="clave-segura-123",
        )
        self.other_user = user_model.objects.create_user(
            username="otro-usuario",
            password="clave-segura-456",
        )

    def test_task_with_time_is_due_fifteen_minutes_before(self):
        Tarea.objects.create(
            usuario=self.user,
            titulo="Entregar planificaci?n",
            fecha_limite=datetime(2026, 7, 30).date(),
            hora_limite=time(18, 0),
        )

        reminders = collect_due_reminders(
            self.user,
            now=aware_local(2026, 7, 30, 17, 45),
        )

        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0]["type"], "task")
        self.assertEqual(
            reminders[0]["title"],
            "Entregar planificaci?n",
        )
        self.assertIn("18:00", reminders[0]["body"])

    def test_date_only_task_is_due_at_nine(self):
        Tarea.objects.create(
            usuario=self.user,
            titulo="Revisar documentos",
            fecha_limite=datetime(2026, 7, 30).date(),
            hora_limite=None,
        )

        reminders = collect_due_reminders(
            self.user,
            now=aware_local(2026, 7, 30, 9, 0),
        )

        self.assertEqual(len(reminders), 1)
        self.assertEqual(
            reminders[0]["body"],
            "Esta tarea vence hoy.",
        )

    def test_completed_task_is_not_returned(self):
        Tarea.objects.create(
            usuario=self.user,
            titulo="Tarea terminada",
            fecha_limite=datetime(2026, 7, 30).date(),
            hora_limite=time(18, 0),
            estado=Tarea.Estado.COMPLETADA,
            completada_en=aware_local(2026, 7, 30, 12, 0),
        )

        reminders = collect_due_reminders(
            self.user,
            now=aware_local(2026, 7, 30, 17, 45),
        )

        self.assertEqual(reminders, [])

    def test_scheduled_event_is_due_one_hour_before(self):
        Evento.objects.create(
            usuario=self.user,
            titulo="Reuni?n docente",
            inicio=aware_local(2026, 7, 30, 19, 0),
            fin=aware_local(2026, 7, 30, 20, 0),
            ubicacion="CeRP",
        )

        reminders = collect_due_reminders(
            self.user,
            now=aware_local(2026, 7, 30, 18, 0),
        )

        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0]["type"], "event")
        self.assertIn("19:00", reminders[0]["body"])
        self.assertIn("CeRP", reminders[0]["body"])

    def test_all_day_event_is_due_at_nine(self):
        Evento.objects.create(
            usuario=self.user,
            titulo="Jornada institucional",
            inicio=aware_local(2026, 7, 30, 0, 0),
            fin=aware_local(2026, 7, 31, 0, 0),
            todo_el_dia=True,
        )

        reminders = collect_due_reminders(
            self.user,
            now=aware_local(2026, 7, 30, 9, 0),
        )

        self.assertEqual(len(reminders), 1)
        self.assertEqual(
            reminders[0]["body"],
            "Evento programado para hoy.",
        )

    def test_cancelled_event_is_not_returned(self):
        Evento.objects.create(
            usuario=self.user,
            titulo="Evento cancelado",
            inicio=aware_local(2026, 7, 30, 19, 0),
            fin=aware_local(2026, 7, 30, 20, 0),
            estado=Evento.Estado.CANCELADO,
        )

        reminders = collect_due_reminders(
            self.user,
            now=aware_local(2026, 7, 30, 18, 45),
        )

        self.assertEqual(reminders, [])

    def test_late_tolerance_accepts_ten_minutes(self):
        Tarea.objects.create(
            usuario=self.user,
            titulo="Aviso reciente",
            fecha_limite=datetime(2026, 7, 30).date(),
            hora_limite=time(18, 0),
        )

        reminders = collect_due_reminders(
            self.user,
            now=aware_local(2026, 7, 30, 17, 55),
        )

        self.assertEqual(len(reminders), 1)

    def test_late_tolerance_rejects_older_reminder(self):
        Tarea.objects.create(
            usuario=self.user,
            titulo="Aviso demasiado antiguo",
            fecha_limite=datetime(2026, 7, 30).date(),
            hora_limite=time(18, 0),
        )

        reminders = collect_due_reminders(
            self.user,
            now=aware_local(2026, 7, 30, 17, 56),
        )

        self.assertEqual(reminders, [])

    def test_task_reminders_can_be_disabled(self):
        PreferenciasUsuario.objects.create(
            usuario=self.user,
            recordatorios_tareas_activos=False,
        )
        Tarea.objects.create(
            usuario=self.user,
            titulo="Tarea sin aviso",
            fecha_limite=datetime(2026, 7, 30).date(),
            hora_limite=time(18, 0),
        )
        Evento.objects.create(
            usuario=self.user,
            titulo="Evento con aviso",
            inicio=aware_local(2026, 7, 30, 18, 0),
            fin=aware_local(2026, 7, 30, 19, 0),
        )

        reminders = collect_due_reminders(
            self.user,
            now=aware_local(2026, 7, 30, 17, 0),
        )

        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0]["type"], "event")

    def test_event_reminders_can_be_disabled(self):
        PreferenciasUsuario.objects.create(
            usuario=self.user,
            recordatorios_eventos_activos=False,
        )
        Tarea.objects.create(
            usuario=self.user,
            titulo="Tarea con aviso",
            fecha_limite=datetime(2026, 7, 30).date(),
            hora_limite=time(18, 0),
        )
        Evento.objects.create(
            usuario=self.user,
            titulo="Evento sin aviso",
            inicio=aware_local(2026, 7, 30, 18, 0),
            fin=aware_local(2026, 7, 30, 19, 0),
        )

        reminders = collect_due_reminders(
            self.user,
            now=aware_local(2026, 7, 30, 17, 45),
        )

        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0]["type"], "task")

    def test_custom_advance_is_applied(self):
        PreferenciasUsuario.objects.create(
            usuario=self.user,
            anticipacion_recordatorios_minutos=30,
        )
        Tarea.objects.create(
            usuario=self.user,
            titulo="Tarea con media hora",
            fecha_limite=datetime(2026, 7, 30).date(),
            hora_limite=time(18, 0),
        )

        reminders = collect_due_reminders(
            self.user,
            now=aware_local(2026, 7, 30, 17, 30),
        )

        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0]["type"], "task")
        self.assertIn("18:00", reminders[0]["body"])

    def test_custom_time_is_used_for_items_without_time(self):
        PreferenciasUsuario.objects.create(
            usuario=self.user,
            hora_recordatorios_sin_hora=time(8, 15),
        )
        Tarea.objects.create(
            usuario=self.user,
            titulo="Tarea sin hora personalizada",
            fecha_limite=datetime(2026, 7, 30).date(),
            hora_limite=None,
        )
        Evento.objects.create(
            usuario=self.user,
            titulo="Evento de todo el dia personalizado",
            inicio=aware_local(2026, 7, 30, 0, 0),
            fin=aware_local(2026, 7, 31, 0, 0),
            todo_el_dia=True,
        )

        reminders = collect_due_reminders(
            self.user,
            now=aware_local(2026, 7, 30, 8, 15),
        )

        self.assertEqual(len(reminders), 2)
        self.assertEqual(
            {item["type"] for item in reminders},
            {"task", "event"},
        )


    def test_other_users_items_are_private(self):
        Tarea.objects.create(
            usuario=self.other_user,
            titulo="Tarea privada ajena",
            fecha_limite=datetime(2026, 7, 30).date(),
            hora_limite=time(18, 0),
        )

        reminders = collect_due_reminders(
            self.user,
            now=aware_local(2026, 7, 30, 17, 45),
        )

        self.assertEqual(reminders, [])


class ReminderEndpointTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="endpoint-recordatorios",
            password="clave-segura-123",
        )

    def test_endpoint_requires_login(self):
        response = self.client.get(
            reverse("agenda:recordatorios_pendientes")
        )

        self.assertEqual(response.status_code, 302)

    def test_endpoint_returns_json_without_cache(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("agenda:recordatorios_pendientes")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ok"], True)
        self.assertEqual(response.json()["reminders"], [])
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_endpoint_rejects_post(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("agenda:recordatorios_pendientes")
        )

        self.assertEqual(response.status_code, 405)
