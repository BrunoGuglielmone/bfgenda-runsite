from datetime import datetime, time, timedelta
import json
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import patch
from uuid import uuid4
import zipfile
from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Categoria, Evento, PreferenciasUsuario, Tarea
from .services.backups import (
    BACKUP_AUTOMATIC,
    BACKUP_MANUAL,
    BACKUP_PRE_RESTORE,
    BackupInfo,
    RestoreResult,
    create_backup,
    list_backups,
    prune_automatic_backups,
    restore_backup,
)


AJAX_HEADERS = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


class AgendaViewsTests(TestCase):
    """Pruebas de los flujos principales y de los componentes dinámicos."""

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="bruno",
            password="clave-segura",
        )
        self.other_user = user_model.objects.create_user(
            username="otra-persona",
            password="otra-clave",
        )
        self.client.force_login(self.user)

    def test_task_form_has_full_page_fallback(self):
        response = self.client.get(reverse("agenda:tarea_crear"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "agenda/formulario.html")
        self.assertContains(response, "Nueva tarea")

    def test_task_modal_uses_selected_date(self):
        response = self.client.get(
            reverse("agenda:tarea_crear"),
            {"fecha": "2026-07-30"},
            **AJAX_HEADERS,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("Nueva tarea", payload["html"])
        self.assertIn("2026-07-30", payload["html"])

    def test_create_task_with_ajax(self):
        response = self.client.post(
            reverse("agenda:tarea_crear"),
            {
                "titulo": "Preparar clase",
                "descripcion": "Revisar materiales",
                "fecha_limite": "2026-07-30",
                "hora_limite": "18:00",
                "prioridad": Tarea.Prioridad.ALTA,
                "categoria": "",
                "return_url": reverse("agenda:tareas_listado"),
            },
            **AJAX_HEADERS,
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["ok"])
        self.assertTrue(
            Tarea.objects.filter(
                usuario=self.user,
                titulo="Preparar clase",
            ).exists()
        )

    def test_create_event_with_ajax(self):
        response = self.client.post(
            reverse("agenda:evento_crear"),
            {
                "titulo": "Reunión de proyecto",
                "descripcion": "",
                "inicio": "2026-07-30T09:00",
                "fin": "2026-07-30T10:00",
                "todo_el_dia": "",
                "ubicacion": "Casa",
                "estado": Evento.Estado.PROGRAMADO,
                "categoria": "",
                "return_url": reverse("agenda:calendario"),
            },
            **AJAX_HEADERS,
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["ok"])
        event = Evento.objects.get(usuario=self.user, titulo="Reunión de proyecto")
        self.assertTrue(timezone.is_aware(event.inicio))

    def test_create_category_with_ajax(self):
        response = self.client.post(
            reverse("agenda:categoria_crear"),
            {
                "nombre": "Trabajo",
                "color": "#3366AA",
                "return_url": reverse("agenda:categorias_listado"),
            },
            **AJAX_HEADERS,
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["ok"])
        self.assertTrue(
            Categoria.objects.filter(
                usuario=self.user,
                nombre="Trabajo",
            ).exists()
        )

    def test_user_cannot_edit_another_users_task(self):
        task = Tarea.objects.create(
            usuario=self.other_user,
            titulo="Tarea privada",
        )

        response = self.client.get(
            reverse("agenda:tarea_editar", args=[task.id]),
            **AJAX_HEADERS,
        )

        self.assertEqual(response.status_code, 404)

    def test_complete_task_with_ajax(self):
        task = Tarea.objects.create(
            usuario=self.user,
            titulo="Finalizar informe",
        )

        response = self.client.post(
            reverse("agenda:tarea_completar", args=[task.id]),
            {"return_url": reverse("agenda:inicio")},
            **AJAX_HEADERS,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        task.refresh_from_db()
        self.assertEqual(task.estado, Tarea.Estado.COMPLETADA)
        self.assertIsNotNone(task.completada_en)

    def test_calendar_contains_user_items_only(self):
        zone = timezone.get_current_timezone()
        Evento.objects.create(
            usuario=self.user,
            titulo="Evento visible",
            inicio=timezone.make_aware(datetime(2026, 7, 30, 9, 0), zone),
            fin=timezone.make_aware(datetime(2026, 7, 30, 10, 0), zone),
        )
        Evento.objects.create(
            usuario=self.other_user,
            titulo="Evento ajeno",
            inicio=timezone.make_aware(datetime(2026, 7, 30, 11, 0), zone),
            fin=timezone.make_aware(datetime(2026, 7, 30, 12, 0), zone),
        )

        response = self.client.get(
            reverse("agenda:calendario"),
            {"vista": "mes", "mes": "2026-07", "dia": "2026-07-30"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Evento visible")
        self.assertNotContains(response, "Evento ajeno")

    def test_calendar_supports_day_week_and_month_views(self):
        for view_name in ("dia", "semana", "mes"):
            with self.subTest(view=view_name):
                response = self.client.get(
                    reverse("agenda:calendario"),
                    {
                        "vista": view_name,
                        "mes": "2026-07",
                        "dia": "2026-07-30",
                    },
                )

                self.assertEqual(response.status_code, 200)
                self.assertContains(
                    response,
                    f'data-calendar-view="{view_name}"',
                )

    def test_dashboard_summary_modal_filters_overdue_tasks(self):
        today = timezone.localdate()
        Tarea.objects.create(
            usuario=self.user,
            titulo="Vencida visible",
            fecha_limite=today - timedelta(days=1),
        )
        Tarea.objects.create(
            usuario=self.user,
            titulo="Pendiente futura",
            fecha_limite=today + timedelta(days=3),
        )

        response = self.client.get(
            reverse("agenda:tareas_resumen"),
            {"tipo": "vencidas"},
            **AJAX_HEADERS,
        )

        self.assertEqual(response.status_code, 200)
        html = response.json()["html"]
        self.assertIn("Vencida visible", html)
        self.assertNotIn("Pendiente futura", html)

    def test_summary_items_link_to_task_list_without_edit_modal(self):
        task = Tarea.objects.create(
            usuario=self.user,
            titulo="Pendiente de consulta rápida",
        )

        response = self.client.get(
            reverse("agenda:tareas_resumen"),
            {"tipo": "pendientes"},
            **AJAX_HEADERS,
        )

        self.assertEqual(response.status_code, 200)
        html = response.json()["html"]
        expected_url = reverse(
            "agenda:tareas_listado",
            query={"filtro": "pendientes"},
            fragment=f"tarea-{task.id}",
        )
        self.assertIn(expected_url, html)
        self.assertNotIn(
            reverse("agenda:tarea_editar", args=[task.id]),
            html,
        )
        self.assertNotIn("data-modal-url", html)

    def test_calendar_items_redirect_to_their_lists_without_edit_modal(self):
        selected_day = timezone.localdate()
        task = Tarea.objects.create(
            usuario=self.user,
            titulo="Tarea visible en calendario",
            fecha_limite=selected_day,
        )
        zone = timezone.get_current_timezone()
        event = Evento.objects.create(
            usuario=self.user,
            titulo="Evento visible en calendario",
            inicio=timezone.make_aware(
                datetime.combine(selected_day, datetime.min.time())
                + timedelta(hours=9),
                zone,
            ),
            fin=timezone.make_aware(
                datetime.combine(selected_day, datetime.min.time())
                + timedelta(hours=10),
                zone,
            ),
        )

        response = self.client.get(
            reverse("agenda:calendario"),
            {"vista": "dia", "dia": selected_day.isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        task_url = reverse(
            "agenda:tareas_listado",
            query={"filtro": "pendientes"},
            fragment=f"tarea-{task.id}",
        )
        event_url = reverse(
            "agenda:eventos_listado",
            query={"filtro": "todos"},
            fragment=f"evento-{event.id}",
        )
        self.assertContains(response, task_url)
        self.assertContains(response, event_url)
        self.assertNotContains(
            response,
            reverse("agenda:tarea_editar", args=[task.id]),
        )
        self.assertNotContains(
            response,
            reverse("agenda:evento_editar", args=[event.id]),
        )

    def test_calendar_day_summary_is_read_only(self):
        selected_day = timezone.localdate()
        task = Tarea.objects.create(
            usuario=self.user,
            titulo="Tarea de lectura",
            fecha_limite=selected_day,
        )

        response = self.client.get(
            reverse("agenda:calendario_dia_resumen"),
            {"fecha": selected_day.isoformat()},
            **AJAX_HEADERS,
        )

        self.assertEqual(response.status_code, 200)
        html = response.json()["html"]
        self.assertIn("Tarea de lectura", html)
        self.assertIn("Ver en Tareas", html)
        self.assertNotIn(reverse("agenda:tarea_editar", args=[task.id]), html)

    def test_weekly_task_creation_links_series_occurrences(self):
        response = self.client.post(
            reverse("agenda:tarea_crear"),
            {
                "titulo": "Planificación semanal",
                "descripcion": "",
                "fecha_limite": "2026-07-30",
                "hora_limite": "18:00",
                "prioridad": Tarea.Prioridad.MEDIA,
                "categoria": "",
                "repetir": "semanal",
                "repetir_hasta": "2026-08-20",
                "fecha_referencia": "2026-07-30",
                "return_url": reverse("agenda:calendario"),
            },
            **AJAX_HEADERS,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            Tarea.objects.filter(
                usuario=self.user,
                titulo="Planificación semanal",
            ).count(),
            4,
        )
        series = Tarea.objects.filter(
            usuario=self.user,
            titulo="Planificación semanal",
        )
        self.assertEqual(
            series.values_list("serie_recurrencia", flat=True).distinct().count(),
            1,
        )
        self.assertIsNotNone(series.first().serie_recurrencia)
        self.assertFalse(series.exclude(tipo_recurrencia="semanal").exists())

    def test_weekly_event_creation_links_series_occurrences(self):
        response = self.client.post(
            reverse("agenda:evento_crear"),
            {
                "titulo": "Reunión semanal",
                "descripcion": "",
                "inicio": "2026-07-30T09:00",
                "fin": "2026-07-30T10:00",
                "todo_el_dia": "",
                "ubicacion": "Casa",
                "estado": Evento.Estado.PROGRAMADO,
                "categoria": "",
                "repetir": "semanal",
                "repetir_hasta": "2026-08-20",
                "fecha_referencia": "2026-07-30",
                "return_url": reverse("agenda:calendario"),
            },
            **AJAX_HEADERS,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            Evento.objects.filter(
                usuario=self.user,
                titulo="Reunión semanal",
            ).count(),
            4,
        )
        series = Evento.objects.filter(
            usuario=self.user,
            titulo="Reunión semanal",
        )
        self.assertEqual(
            series.values_list("serie_recurrencia", flat=True).distinct().count(),
            1,
        )
        self.assertIsNotNone(series.first().serie_recurrencia)
        self.assertFalse(series.exclude(tipo_recurrencia="semanal").exists())

    def test_monthly_task_creation_uses_same_day_number(self):
        response = self.client.post(
            reverse("agenda:tarea_crear"),
            {
                "titulo": "Pago mensual",
                "descripcion": "",
                "fecha_limite": "2026-07-20",
                "hora_limite": "18:00",
                "prioridad": Tarea.Prioridad.MEDIA,
                "categoria": "",
                "repetir": "mensual",
                "repetir_hasta": "2026-10-20",
                "fecha_referencia": "2026-07-20",
                "return_url": reverse("agenda:calendario"),
            },
            **AJAX_HEADERS,
        )

        self.assertEqual(response.status_code, 201)
        dates = list(
            Tarea.objects.filter(
                usuario=self.user,
                titulo="Pago mensual",
            )
            .order_by("fecha_limite")
            .values_list("fecha_limite", flat=True)
        )
        self.assertEqual(
            [value.isoformat() for value in dates],
            [
                "2026-07-20",
                "2026-08-20",
                "2026-09-20",
                "2026-10-20",
            ],
        )

    def test_monthly_event_creation_uses_same_day_number(self):
        response = self.client.post(
            reverse("agenda:evento_crear"),
            {
                "titulo": "Reunión mensual",
                "descripcion": "",
                "inicio": "2026-07-18T09:00",
                "fin": "2026-07-18T10:00",
                "todo_el_dia": "",
                "ubicacion": "Casa",
                "estado": Evento.Estado.PROGRAMADO,
                "categoria": "",
                "repetir": "mensual",
                "repetir_hasta": "2026-10-18",
                "fecha_referencia": "2026-07-18",
                "return_url": reverse("agenda:calendario"),
            },
            **AJAX_HEADERS,
        )

        self.assertEqual(response.status_code, 201)
        dates = [
            timezone.localtime(value).date().isoformat()
            for value in Evento.objects.filter(
                usuario=self.user,
                titulo="Reunión mensual",
            )
            .order_by("inicio")
            .values_list("inicio", flat=True)
        ]
        self.assertEqual(
            dates,
            [
                "2026-07-18",
                "2026-08-18",
                "2026-09-18",
                "2026-10-18",
            ],
        )

    def test_monthly_recurrence_skips_months_without_selected_day(self):
        response = self.client.post(
            reverse("agenda:tarea_crear"),
            {
                "titulo": "Cierre de mes",
                "descripcion": "",
                "fecha_limite": "2027-01-31",
                "hora_limite": "",
                "prioridad": Tarea.Prioridad.MEDIA,
                "categoria": "",
                "repetir": "mensual",
                "repetir_hasta": "2027-04-30",
                "fecha_referencia": "2027-01-31",
                "return_url": reverse("agenda:calendario"),
            },
            **AJAX_HEADERS,
        )

        self.assertEqual(response.status_code, 201)
        dates = list(
            Tarea.objects.filter(
                usuario=self.user,
                titulo="Cierre de mes",
            )
            .order_by("fecha_limite")
            .values_list("fecha_limite", flat=True)
        )
        self.assertEqual(
            [value.isoformat() for value in dates],
            ["2027-01-31", "2027-03-31"],
        )

    def test_calendar_shows_monthly_action_and_hides_events_shortcut(self):
        response = self.client.get(
            reverse("agenda:calendario"),
            {"vista": "mes", "mes": "2026-07", "dia": "2026-07-20"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Todos los 20")
        self.assertContains(response, "repetir=mensual")
        events_shortcut = reverse(
            "agenda:eventos_listado",
            query={"filtro": "proximos"},
        )
        self.assertNotContains(response, f'href="{events_shortcut}"')

    def test_recurring_task_series_can_be_deleted_from_calendar(self):
        selected_day = timezone.localdate()
        series_id = uuid4()
        first = Tarea.objects.create(
            usuario=self.user,
            titulo="Preparación semanal",
            fecha_limite=selected_day,
            serie_recurrencia=series_id,
            tipo_recurrencia="semanal",
        )
        Tarea.objects.create(
            usuario=self.user,
            titulo="Preparación semanal",
            fecha_limite=selected_day + timedelta(days=7),
            serie_recurrencia=series_id,
            tipo_recurrencia="semanal",
        )
        other_task = Tarea.objects.create(
            usuario=self.other_user,
            titulo="Serie ajena",
            fecha_limite=selected_day,
            serie_recurrencia=series_id,
            tipo_recurrencia="semanal",
        )
        independent = Tarea.objects.create(
            usuario=self.user,
            titulo="Tarea independiente",
            fecha_limite=selected_day,
        )
        delete_url = reverse("agenda:tarea_serie_eliminar", args=[first.id])

        calendar_response = self.client.get(
            reverse("agenda:calendario"),
            {"vista": "dia", "dia": selected_day.isoformat()},
        )
        self.assertContains(calendar_response, "Serie semanal")
        self.assertContains(calendar_response, delete_url)
        self.assertContains(calendar_response, "Eliminar serie")

        confirmation = self.client.get(delete_url, **AJAX_HEADERS)
        self.assertEqual(confirmation.status_code, 200)
        self.assertIn("2 tareas incluidas", confirmation.json()["html"])
        self.assertEqual(
            Tarea.objects.filter(
                usuario=self.user,
                serie_recurrencia=series_id,
            ).count(),
            2,
        )

        response = self.client.post(
            delete_url,
            {"return_url": reverse("agenda:calendario")},
            **AJAX_HEADERS,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Tarea.objects.filter(
                usuario=self.user,
                serie_recurrencia=series_id,
            ).exists()
        )
        self.assertTrue(Tarea.objects.filter(id=other_task.id).exists())
        self.assertTrue(Tarea.objects.filter(id=independent.id).exists())

    def test_recurring_event_series_deletion_is_scoped_to_its_owner(self):
        selected_day = timezone.localdate()
        start = timezone.make_aware(
            datetime.combine(selected_day, time(9, 0)),
            timezone.get_current_timezone(),
        )
        series_id = uuid4()
        first = Evento.objects.create(
            usuario=self.user,
            titulo="Reunión mensual",
            inicio=start,
            fin=start + timedelta(hours=1),
            serie_recurrencia=series_id,
            tipo_recurrencia="mensual",
        )
        Evento.objects.create(
            usuario=self.user,
            titulo="Reunión mensual",
            inicio=start + timedelta(days=31),
            fin=start + timedelta(days=31, hours=1),
            serie_recurrencia=series_id,
            tipo_recurrencia="mensual",
        )
        other_event = Evento.objects.create(
            usuario=self.other_user,
            titulo="Serie ajena",
            inicio=start,
            fin=start + timedelta(hours=1),
            serie_recurrencia=series_id,
            tipo_recurrencia="mensual",
        )
        delete_url = reverse("agenda:evento_serie_eliminar", args=[first.id])

        confirmation = self.client.get(delete_url, **AJAX_HEADERS)
        self.assertEqual(confirmation.status_code, 200)
        self.assertIn("2 eventos incluidos", confirmation.json()["html"])

        response = self.client.post(delete_url, **AJAX_HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Evento.objects.filter(
                usuario=self.user,
                serie_recurrencia=series_id,
            ).exists()
        )
        self.assertTrue(Evento.objects.filter(id=other_event.id).exists())

        forbidden = self.client.get(
            reverse("agenda:evento_serie_eliminar", args=[other_event.id]),
            **AJAX_HEADERS,
        )
        self.assertEqual(forbidden.status_code, 404)

    def test_old_undated_tasks_trigger_daily_dashboard_reminder(self):
        old_task = Tarea.objects.create(
            usuario=self.user,
            titulo="Tarea olvidada",
        )
        Tarea.objects.filter(id=old_task.id).update(
            creada_en=timezone.now() - timedelta(days=8)
        )

        first_response = self.client.get(reverse("agenda:inicio"))
        second_response = self.client.get(reverse("agenda:inicio"))

        self.assertContains(first_response, "data-auto-modal-url")
        self.assertNotContains(second_response, "data-auto-modal-url")

    def test_event_edit_link_only_appears_in_events_section(self):
        zone = timezone.get_current_timezone()
        event = Evento.objects.create(
            usuario=self.user,
            titulo="Evento editable",
            inicio=timezone.make_aware(datetime(2026, 7, 30, 9, 0), zone),
            fin=timezone.make_aware(datetime(2026, 7, 30, 10, 0), zone),
        )
        edit_url = reverse("agenda:evento_editar", args=[event.id])

        calendar_response = self.client.get(
            reverse("agenda:calendario"),
            {"vista": "dia", "dia": "2026-07-30"},
        )
        events_response = self.client.get(
            reverse("agenda:eventos_listado"),
            {"filtro": "todos"},
        )

        self.assertNotContains(calendar_response, edit_url)
        self.assertContains(events_response, f'data-modal-url="{edit_url}"')

    def test_completed_tasks_older_than_two_months_are_removed(self):
        old_task = Tarea.objects.create(
            usuario=self.user,
            titulo="Completada antigua",
            estado=Tarea.Estado.COMPLETADA,
            completada_en=timezone.now() - timedelta(days=70),
        )
        recent_task = Tarea.objects.create(
            usuario=self.user,
            titulo="Completada reciente",
            estado=Tarea.Estado.COMPLETADA,
            completada_en=timezone.now() - timedelta(days=20),
        )

        response = self.client.get(reverse("agenda:inicio"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Tarea.objects.filter(id=old_task.id).exists())
        self.assertTrue(Tarea.objects.filter(id=recent_task.id).exists())

    def test_task_deletion_requires_confirmation_and_post(self):
        task = Tarea.objects.create(
            usuario=self.user,
            titulo="Tarea para eliminar",
        )
        delete_url = reverse("agenda:tarea_eliminar", args=[task.id])

        confirmation = self.client.get(delete_url, **AJAX_HEADERS)

        self.assertEqual(confirmation.status_code, 200)
        self.assertTrue(confirmation.json()["ok"])
        self.assertIn("¿Eliminar", confirmation.json()["html"])
        self.assertTrue(Tarea.objects.filter(id=task.id).exists())

        deletion = self.client.post(
            delete_url,
            {"return_url": reverse("agenda:tareas_listado")},
            **AJAX_HEADERS,
        )

        self.assertEqual(deletion.status_code, 200)
        self.assertTrue(deletion.json()["ok"])
        self.assertFalse(Tarea.objects.filter(id=task.id).exists())

    def test_event_deletion_requires_confirmation_and_post(self):
        zone = timezone.get_current_timezone()
        event = Evento.objects.create(
            usuario=self.user,
            titulo="Evento para eliminar",
            inicio=timezone.make_aware(datetime(2026, 7, 30, 9, 0), zone),
            fin=timezone.make_aware(datetime(2026, 7, 30, 10, 0), zone),
        )
        delete_url = reverse("agenda:evento_eliminar", args=[event.id])

        confirmation = self.client.get(delete_url, **AJAX_HEADERS)

        self.assertEqual(confirmation.status_code, 200)
        self.assertIn("Evento para eliminar", confirmation.json()["html"])
        self.assertTrue(Evento.objects.filter(id=event.id).exists())

        deletion = self.client.post(
            delete_url,
            {"return_url": reverse("agenda:eventos_listado")},
            **AJAX_HEADERS,
        )

        self.assertEqual(deletion.status_code, 200)
        self.assertFalse(Evento.objects.filter(id=event.id).exists())

    def test_category_deletion_keeps_related_items_without_category(self):
        zone = timezone.get_current_timezone()
        category = Categoria.objects.create(
            usuario=self.user,
            nombre="Temporal",
            color="#334455",
        )
        task = Tarea.objects.create(
            usuario=self.user,
            categoria=category,
            titulo="Tarea categorizada",
        )
        event = Evento.objects.create(
            usuario=self.user,
            categoria=category,
            titulo="Evento categorizado",
            inicio=timezone.make_aware(datetime(2026, 7, 30, 9, 0), zone),
            fin=timezone.make_aware(datetime(2026, 7, 30, 10, 0), zone),
        )

        response = self.client.post(
            reverse("agenda:categoria_eliminar", args=[category.id]),
            {"return_url": reverse("agenda:categorias_listado")},
            **AJAX_HEADERS,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Categoria.objects.filter(id=category.id).exists())
        task.refresh_from_db()
        event.refresh_from_db()
        self.assertIsNone(task.categoria)
        self.assertIsNone(event.categoria)

    def test_user_cannot_delete_another_users_items(self):
        task = Tarea.objects.create(
            usuario=self.other_user,
            titulo="Tarea ajena",
        )

        response = self.client.post(
            reverse("agenda:tarea_eliminar", args=[task.id]),
            {"return_url": reverse("agenda:tareas_listado")},
            **AJAX_HEADERS,
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Tarea.objects.filter(id=task.id).exists())

    def test_task_list_shows_accessible_complete_and_restore_actions(self):
        pending_task = Tarea.objects.create(
            usuario=self.user,
            titulo="Completar informe",
        )
        completed_task = Tarea.objects.create(
            usuario=self.user,
            titulo="Restaurar informe",
            estado=Tarea.Estado.COMPLETADA,
            completada_en=timezone.now(),
        )

        response = self.client.get(
            reverse("agenda:tareas_listado"),
            {"filtro": "todas"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'aria-label="Completar tarea Completar informe"',
        )
        self.assertContains(
            response,
            'aria-label="Restaurar tarea Restaurar informe"',
        )
        self.assertContains(
            response,
            reverse(
                "agenda:tarea_completar",
                args=[pending_task.id],
            ),
        )
        self.assertContains(
            response,
            reverse(
                "agenda:tarea_restaurar",
                args=[completed_task.id],
            ),
        )

    def test_task_list_shows_accessible_edit_and_delete_actions(self):
        task = Tarea.objects.create(
            usuario=self.user,
            titulo="Preparar clase",
        )

        response = self.client.get(
            reverse("agenda:tareas_listado")
        )

        edit_url = reverse(
            "agenda:tarea_editar",
            args=[task.id],
        )
        delete_url = reverse(
            "agenda:tarea_eliminar",
            args=[task.id],
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'data-modal-url="{edit_url}"',
        )
        self.assertContains(
            response,
            f'data-modal-url="{delete_url}"',
        )
        self.assertContains(
            response,
            'aria-label="Editar tarea Preparar clase"',
        )
        self.assertContains(
            response,
            'aria-label="Eliminar tarea Preparar clase"',
        )
        self.assertContains(
            response,
            'class="task-action-icon"',
        )

    def test_event_list_shows_accessible_actions(self):
        zone = timezone.get_current_timezone()
        event = Evento.objects.create(
            usuario=self.user,
            titulo="Reunión de coordinación",
            inicio=timezone.make_aware(
                datetime(2026, 7, 30, 9, 0),
                zone,
            ),
            fin=timezone.make_aware(
                datetime(2026, 7, 30, 10, 0),
                zone,
            ),
        )

        response = self.client.get(
            reverse("agenda:eventos_listado"),
            {"filtro": "todos"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'aria-label="Editar evento Reunión de coordinación"',
        )
        self.assertContains(
            response,
            'aria-label="Eliminar evento Reunión de coordinación"',
        )
        self.assertContains(
            response,
            'class="event-action-icon"',
        )

    def test_category_list_shows_accessible_actions(self):
        active_category = Categoria.objects.create(
            usuario=self.user,
            nombre="Trabajo",
            activa=True,
        )
        inactive_category = Categoria.objects.create(
            usuario=self.user,
            nombre="Estudio",
            activa=False,
        )

        response = self.client.get(
            reverse("agenda:categorias_listado")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'aria-label="Editar categoría Trabajo"',
        )
        self.assertContains(
            response,
            'aria-label="Eliminar categoría Trabajo"',
        )
        self.assertContains(
            response,
            'aria-label="Desactivar categoría Trabajo"',
        )
        self.assertContains(
            response,
            'aria-label="Activar categoría Estudio"',
        )
        self.assertContains(
            response,
            'class="category-action-icon"',
        )

    def test_management_lists_show_delete_actions(self):
        zone = timezone.get_current_timezone()
        task = Tarea.objects.create(usuario=self.user, titulo="Tarea visible")
        event = Evento.objects.create(
            usuario=self.user,
            titulo="Evento visible",
            inicio=timezone.make_aware(datetime(2026, 7, 30, 9, 0), zone),
            fin=timezone.make_aware(datetime(2026, 7, 30, 10, 0), zone),
        )
        category = Categoria.objects.create(
            usuario=self.user,
            nombre="Visible",
        )

        task_response = self.client.get(reverse("agenda:tareas_listado"))
        event_response = self.client.get(
            reverse("agenda:eventos_listado"),
            {"filtro": "todos"},
        )
        category_response = self.client.get(reverse("agenda:categorias_listado"))

        self.assertContains(
            task_response,
            reverse("agenda:tarea_eliminar", args=[task.id]),
        )
        self.assertContains(
            event_response,
            reverse("agenda:evento_eliminar", args=[event.id]),
        )
        self.assertContains(
            category_response,
            reverse("agenda:categoria_eliminar", args=[category.id]),
        )


    def test_configuration_creates_default_user_preferences(self):
        response = self.client.get(reverse("agenda:configuracion"))

        self.assertEqual(response.status_code, 200)
        preferences = PreferenciasUsuario.objects.get(usuario=self.user)
        self.assertEqual(
            preferences.vista_calendario,
            PreferenciasUsuario.VistaCalendario.MES,
        )
        self.assertEqual(
            preferences.tema_interfaz,
            PreferenciasUsuario.TemaInterfaz.SISTEMA,
        )
        self.assertEqual(preferences.duracion_evento_minutos, 60)
        self.assertTrue(preferences.avisos_sin_fecha_activos)
        self.assertTrue(preferences.recordatorios_tareas_activos)
        self.assertTrue(preferences.recordatorios_eventos_activos)
        self.assertEqual(
            preferences.anticipacion_recordatorios_minutos,
            15,
        )
        self.assertEqual(
            preferences.hora_recordatorios_sin_hora.strftime("%H:%M"),
            "09:00",
        )

    def test_configuration_shows_reminder_summary(self):
        preferences = PreferenciasUsuario.objects.create(
            usuario=self.user,
            recordatorios_tareas_activos=True,
            recordatorios_eventos_activos=False,
            anticipacion_recordatorios_minutos=30,
            hora_recordatorios_sin_hora=time(8, 15),
        )

        response = self.client.get(
            reverse("agenda:configuracion")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Recordatorios automáticos",
        )
        self.assertContains(
            response,
            "30 minutos antes",
        )
        self.assertContains(
            response,
            "08:15",
        )
        self.assertContains(response, "Activos")
        self.assertContains(response, "Desactivados")
        self.assertEqual(
            response.context["preferencias"],
            preferences,
        )

    def test_configuration_shows_configurable_reminder_fields(self):
        response = self.client.get(
            reverse("agenda:configuracion_editar"),
            **AJAX_HEADERS,
        )

        self.assertEqual(response.status_code, 200)
        html = response.json()["html"]

        self.assertIn(
            'name="tema_interfaz"',
            html,
        )
        self.assertIn(
            'name="recordatorios_tareas_activos"',
            html,
        )
        self.assertIn(
            'name="recordatorios_eventos_activos"',
            html,
        )
        self.assertIn(
            'name="anticipacion_recordatorios_minutos"',
            html,
        )
        self.assertIn(
            'name="anticipacion_eventos_minutos"',
            html,
        )
        self.assertIn(
            'name="hora_recordatorios_sin_hora"',
            html,
        )

    def test_preferences_can_be_updated_with_ajax(self):
        response = self.client.post(
            reverse("agenda:configuracion_editar"),
            {
                "tema_interfaz": PreferenciasUsuario.TemaInterfaz.OSCURO,
                "vista_calendario": PreferenciasUsuario.VistaCalendario.SEMANA,
                "hora_inicio_evento": "14:30",
                "duracion_evento_minutos": "90",
                "avisos_sin_fecha_activos": "on",
                "dias_aviso_sin_fecha": "14",
                "recordatorios_tareas_activos": "on",
                "anticipacion_recordatorios_minutos": "30",
                "anticipacion_eventos_minutos": "120",
                "hora_recordatorios_sin_hora": "08:15",
                "return_url": reverse("agenda:configuracion"),
            },
            **AJAX_HEADERS,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        preferences = PreferenciasUsuario.objects.get(usuario=self.user)
        self.assertEqual(
            preferences.tema_interfaz,
            PreferenciasUsuario.TemaInterfaz.OSCURO,
        )
        self.assertEqual(
            preferences.vista_calendario,
            PreferenciasUsuario.VistaCalendario.SEMANA,
        )
        self.assertEqual(preferences.hora_inicio_evento.strftime("%H:%M"), "14:30")
        self.assertEqual(preferences.duracion_evento_minutos, 90)
        self.assertEqual(preferences.dias_aviso_sin_fecha, 14)
        self.assertTrue(preferences.recordatorios_tareas_activos)
        self.assertFalse(preferences.recordatorios_eventos_activos)
        self.assertEqual(
            preferences.anticipacion_recordatorios_minutos,
            30,
        )
        self.assertEqual(
            preferences.anticipacion_eventos_minutos,
            120,
        )
        self.assertEqual(
            preferences.hora_recordatorios_sin_hora.strftime("%H:%M"),
            "08:15",
        )

    def test_calendar_uses_configured_default_view(self):
        PreferenciasUsuario.objects.create(
            usuario=self.user,
            vista_calendario=PreferenciasUsuario.VistaCalendario.SEMANA,
        )

        response = self.client.get(reverse("agenda:calendario"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-calendar-view="semana"')

    def test_event_form_uses_configured_initial_time_and_duration(self):
        PreferenciasUsuario.objects.create(
            usuario=self.user,
            hora_inicio_evento=time(14, 30),
            duracion_evento_minutos=90,
        )

        response = self.client.get(
            reverse("agenda:evento_crear"),
            {"fecha": "2026-07-30"},
            **AJAX_HEADERS,
        )

        self.assertEqual(response.status_code, 200)
        html = response.json()["html"]
        self.assertIn("2026-07-30T14:30", html)
        self.assertIn("2026-07-30T16:00", html)

    def test_disabled_undated_reminder_does_not_open_automatically(self):
        PreferenciasUsuario.objects.create(
            usuario=self.user,
            avisos_sin_fecha_activos=False,
            dias_aviso_sin_fecha=1,
        )
        old_task = Tarea.objects.create(
            usuario=self.user,
            titulo="Tarea antigua sin aviso",
        )
        Tarea.objects.filter(id=old_task.id).update(
            creada_en=timezone.now() - timedelta(days=20)
        )

        response = self.client.get(reverse("agenda:inicio"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-auto-modal-url")


class BackupServiceTests(SimpleTestCase):
    """Pruebas de las copias SQLite sin depender de la base de pruebas Django."""

    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.database_path = root / "db.sqlite3"
        self.backup_dir = root / "backups"
        self._create_database("estado-inicial")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _create_database(self, marker):
        connection = sqlite3.connect(self.database_path)
        try:
            for table in (
                "auth_user",
                "agenda_categoria",
                "agenda_evento",
                "agenda_tarea",
            ):
                connection.execute(
                    f'CREATE TABLE IF NOT EXISTS "{table}" '
                    "(id INTEGER)"
                )

            connection.execute(
                "CREATE TABLE IF NOT EXISTS django_migrations ("
                "id INTEGER, "
                "app TEXT NOT NULL, "
                "name TEXT NOT NULL)"
            )

            connection.execute(
                "CREATE TABLE IF NOT EXISTS test_marker (value TEXT)"
            )
            connection.execute("DELETE FROM test_marker")
            connection.execute(
                "INSERT INTO test_marker(value) VALUES (?)",
                (marker,),
            )
            connection.commit()
        finally:
            connection.close()

    def _marker(self):
        connection = sqlite3.connect(self.database_path)
        try:
            return connection.execute(
                "SELECT value FROM test_marker"
            ).fetchone()[0]
        finally:
            connection.close()

    def test_manual_backup_is_created_and_listed(self):
        backup = create_backup(
            BACKUP_MANUAL,
            database_path=self.database_path,
            backup_dir=self.backup_dir,
            now=datetime(2026, 7, 27, 8, 0),
        )

        self.assertTrue(backup.path.exists())
        self.assertTrue(
            backup.name.startswith("bfgenda-manual-")
        )
        self.assertEqual(backup.kind, BACKUP_MANUAL)
        self.assertEqual([item.name for item in list_backups(backup_dir=self.backup_dir)], [backup.name])

    def test_legacy_agende_backup_is_still_listed(self):
        backup = create_backup(
            BACKUP_MANUAL,
            database_path=self.database_path,
            backup_dir=self.backup_dir,
            now=datetime(2026, 7, 27, 8, 0),
        )
        legacy_path = backup.path.with_name(
            backup.name.replace("bfgenda-", "agende-", 1)
        )
        backup.path.rename(legacy_path)

        listed = list_backups(backup_dir=self.backup_dir)

        self.assertEqual(
            [item.name for item in listed],
            [legacy_path.name],
        )

    def test_automatic_backup_pruning_keeps_newest_files(self):
        for hour in (8, 9, 10):
            create_backup(
                BACKUP_AUTOMATIC,
                database_path=self.database_path,
                backup_dir=self.backup_dir,
                now=datetime(2026, 7, 27, hour, 0),
            )

        removed = prune_automatic_backups(
            backup_dir=self.backup_dir,
            limit=2,
        )
        remaining = [
            backup
            for backup in list_backups(backup_dir=self.backup_dir)
            if backup.kind == BACKUP_AUTOMATIC
        ]

        self.assertEqual(removed, 1)
        self.assertEqual(len(remaining), 2)
        self.assertEqual(remaining[0].created_at.hour, 10)

    def test_restore_recovers_selected_database_and_creates_safety_copy(self):
        selected = create_backup(
            BACKUP_MANUAL,
            database_path=self.database_path,
            backup_dir=self.backup_dir,
            now=datetime(2026, 7, 27, 8, 0),
        )
        self._create_database("estado-modificado")

        result = restore_backup(
            selected.name,
            database_path=self.database_path,
            backup_dir=self.backup_dir,
            now=datetime(2026, 7, 27, 9, 0),
        )

        self.assertEqual(self._marker(), "estado-inicial")
        self.assertTrue(result.safety_backup.path.exists())
        self.assertEqual(result.safety_backup.kind, "pre-restore")


    def test_restore_recovers_previous_state_after_partial_failure(self):
        from agenda.services import backups as backup_service
        from agenda.services.backups import BackupError
        from agenda.services.maintenance import maintenance_is_active

        selected = create_backup(
            BACKUP_MANUAL,
            database_path=self.database_path,
            backup_dir=self.backup_dir,
            now=datetime(2026, 7, 27, 8, 0),
        )
        self._create_database("estado-antes-del-fallo")

        original_copy = backup_service._copy_database_with_sqlite
        copy_calls = 0

        def copy_then_fail(source_path, destination_path):
            nonlocal copy_calls
            copy_calls += 1

            original_copy(source_path, destination_path)

            # Primera llamada: creaci?n de la copia preventiva.
            # Segunda llamada: reemplazo con la copia seleccionada.
            if copy_calls == 2:
                raise sqlite3.DatabaseError(
                    "fallo simulado despues del reemplazo"
                )

        with patch(
            "agenda.services.backups._copy_database_with_sqlite",
            side_effect=copy_then_fail,
        ):
            with self.assertRaisesRegex(
                BackupError,
                "Se recupero el estado anterior",
            ):
                restore_backup(
                    selected.name,
                    database_path=self.database_path,
                    backup_dir=self.backup_dir,
                    now=datetime(2026, 7, 27, 9, 0),
                )

        self.assertEqual(
            self._marker(),
            "estado-antes-del-fallo",
        )
        self.assertEqual(copy_calls, 3)
        self.assertFalse(maintenance_is_active())

        safety_backups = [
            backup
            for backup in list_backups(
                backup_dir=self.backup_dir
            )
            if backup.kind == BACKUP_PRE_RESTORE
        ]

        self.assertEqual(len(safety_backups), 1)


    def test_validation_rejects_backup_with_missing_column(self):
        from agenda.services.backups import (
            BackupError,
            validate_sqlite_database,
        )

        reference_path = self.database_path.with_name(
            "reference.sqlite3"
        )
        reference_connection = sqlite3.connect(reference_path)

        try:
            for table in (
                "auth_user",
                "agenda_categoria",
                "agenda_evento",
                "agenda_tarea",
                "django_migrations",
            ):
                reference_connection.execute(
                    f'CREATE TABLE "{table}" ('
                    'id INTEGER, required_value TEXT)'
                )

            reference_connection.commit()
        finally:
            reference_connection.close()

        with self.assertRaisesRegex(
            BackupError,
            "faltan columnas",
        ):
            validate_sqlite_database(
                self.database_path,
                reference_path=reference_path,
            )

    def test_validation_rejects_backup_with_missing_migration(self):
        from agenda.services.backups import (
            BackupError,
            validate_sqlite_database,
        )

        reference_path = self.database_path.with_name(
            "migration-reference.sqlite3"
        )
        reference_connection = sqlite3.connect(reference_path)

        try:
            for table in (
                "auth_user",
                "agenda_categoria",
                "agenda_evento",
                "agenda_tarea",
            ):
                reference_connection.execute(
                    f'CREATE TABLE "{table}" (id INTEGER)'
                )

            reference_connection.execute(
                "CREATE TABLE django_migrations ("
                "id INTEGER, app TEXT, name TEXT)"
            )
            reference_connection.execute(
                "INSERT INTO django_migrations(app, name) "
                "VALUES (?, ?)",
                ("agenda", "9999_future_schema"),
            )
            reference_connection.commit()
        finally:
            reference_connection.close()

        with self.assertRaisesRegex(
            BackupError,
            "Faltan migraciones",
        ):
            validate_sqlite_database(
                self.database_path,
                reference_path=reference_path,
            )


@override_settings(AGENDE_AUTOMATIC_BACKUPS=False)
class AgendaDataViewsTests(TestCase):
    """Pruebas de exportación y controles HTTP de la sección Datos."""

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="bruno-datos",
            password="clave-segura",
        )
        self.other_user = user_model.objects.create_user(
            username="otra-persona-datos",
            password="otra-clave",
        )
        self.client.force_login(self.user)
        self.category = Categoria.objects.create(
            usuario=self.user,
            nombre="Estudio",
            color="#6657D9",
        )
        Tarea.objects.create(
            usuario=self.user,
            categoria=self.category,
            titulo="Tarea exportada",
        )
        Tarea.objects.create(
            usuario=self.other_user,
            titulo="Tarea ajena",
        )
        zone = timezone.get_current_timezone()
        Evento.objects.create(
            usuario=self.user,
            categoria=self.category,
            titulo="Evento exportado",
            inicio=timezone.make_aware(datetime(2026, 7, 30, 9, 0), zone),
            fin=timezone.make_aware(datetime(2026, 7, 30, 10, 0), zone),
        )

    def test_configuration_shows_backup_and_export_section(self):
        with tempfile.TemporaryDirectory() as directory:
            with override_settings(AGENDE_BACKUP_DIR=Path(directory)):
                response = self.client.get(reverse("agenda:configuracion"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Datos y copias de seguridad")
        self.assertContains(response, reverse("agenda:exportar_json"))
        self.assertContains(response, reverse("agenda:exportar_csv"))

    def test_json_export_contains_only_authenticated_users_data(self):
        response = self.client.get(reverse("agenda:exportar_json"))
        payload = json.loads(response.content.decode("utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json; charset=utf-8")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(
            "bfgenda-datos-",
            response["Content-Disposition"],
        )
        titles = [task["title"] for task in payload["tasks"]]
        self.assertIn("Tarea exportada", titles)
        self.assertNotIn("Tarea ajena", titles)

    def test_logical_backup_is_restorable_and_excludes_other_users(self):
        response = self.client.get(
            reverse("agenda:exportar_respaldo_logico")
        )
        fixture = json.loads(response.content.decode("utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "bfgenda-respaldo-logico-",
            response["Content-Disposition"],
        )
        users = [
            item for item in fixture if item["model"] == "auth.user"
        ]
        task_titles = [
            item["fields"]["titulo"]
            for item in fixture
            if item["model"] == "agenda.tarea"
        ]
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["fields"]["username"], "bruno-datos")
        self.assertIn("Tarea exportada", task_titles)
        self.assertNotIn("Tarea ajena", task_titles)

    @patch(
        "agenda.views.preferences.sqlite_backups_enabled",
        return_value=False,
    )
    def test_managed_database_hides_sqlite_restore_controls(
        self,
        mocked_enabled,
    ):
        response = self.client.get(reverse("agenda:configuracion"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Neon PostgreSQL")
        self.assertContains(
            response,
            reverse("agenda:exportar_respaldo_logico"),
        )
        self.assertNotContains(response, "Crear copia ahora")
        self.assertNotContains(response, "Restaurar reemplaza")
        mocked_enabled.assert_called_once_with()

    def test_csv_export_contains_expected_files(self):
        response = self.client.get(reverse("agenda:exportar_csv"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertIn(
            "bfgenda-csv-",
            response["Content-Disposition"],
        )

        with zipfile.ZipFile(BytesIO(response.content)) as archive:
            names = set(archive.namelist())
            self.assertIn("tareas.csv", names)
            self.assertIn("eventos.csv", names)
            self.assertIn("categorias.csv", names)
            task_csv = archive.read("tareas.csv").decode("utf-8-sig")
            self.assertIn("Tarea exportada", task_csv)
            self.assertNotIn("Tarea ajena", task_csv)

    def test_manual_backup_action_uses_dynamic_response(self):
        fake = BackupInfo(
            name="bfgenda-manual-20260727-120000-000000.sqlite3",
            path=Path("fake.sqlite3"),
            kind=BACKUP_MANUAL,
            created_at=timezone.now(),
            size_bytes=1024,
        )

        with patch("agenda.views.data.create_backup", return_value=fake):
            response = self.client.post(
                reverse("agenda:backup_crear"),
                {"return_url": reverse("agenda:configuracion")},
                **AJAX_HEADERS,
            )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["ok"])
        self.assertIn(fake.name, response.json()["message"])

    def test_restore_confirmation_and_action_are_protected(self):
        with tempfile.TemporaryDirectory() as directory:
            backup_dir = Path(directory)
            name = "agende-manual-20260727-120000-000000.sqlite3"
            path = backup_dir / name
            path.write_bytes(b"x" * 200)
            info = BackupInfo(
                name=name,
                path=path,
                kind=BACKUP_MANUAL,
                created_at=timezone.now(),
                size_bytes=200,
            )
            result = RestoreResult(restored_backup=info, safety_backup=info)

            with override_settings(AGENDE_BACKUP_DIR=backup_dir):
                confirmation = self.client.get(
                    reverse("agenda:backup_restaurar", args=[name]),
                    **AJAX_HEADERS,
                )
                with patch("agenda.views.data.restore_backup", return_value=result):
                    restored = self.client.post(
                        reverse("agenda:backup_restaurar", args=[name]),
                        {"return_url": reverse("agenda:configuracion")},
                        **AJAX_HEADERS,
                    )

        self.assertEqual(confirmation.status_code, 200)
        self.assertIn("Reemplazar los datos actuales", confirmation.json()["html"])
        self.assertEqual(restored.status_code, 200)
        self.assertTrue(restored.json()["hard_reload"])
        self.assertEqual(restored.json()["redirect_url"], reverse("login"))


class GlobalSearchTests(TestCase):
    """Pruebas de la búsqueda global y de sus accesos de solo lectura."""

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="bruno-busqueda",
            password="clave-segura",
        )
        self.other_user = user_model.objects.create_user(
            username="otra-busqueda",
            password="otra-clave",
        )
        self.client.force_login(self.user)

        self.category = Categoria.objects.create(
            usuario=self.user,
            nombre="Trabajo docente",
            color="#6657D9",
        )
        self.task = Tarea.objects.create(
            usuario=self.user,
            categoria=self.category,
            titulo="Preparar planificación",
            descripcion="Revisar materiales para la clase",
            fecha_limite=timezone.localdate() + timedelta(days=2),
        )
        Tarea.objects.create(
            usuario=self.other_user,
            titulo="Planificación privada ajena",
        )

        zone = timezone.get_current_timezone()
        self.event = Evento.objects.create(
            usuario=self.user,
            categoria=self.category,
            titulo="Reunión de coordinación",
            descripcion="Coordinar la próxima unidad",
            ubicacion="CeRP",
            inicio=timezone.make_aware(datetime(2026, 8, 10, 14, 0), zone),
            fin=timezone.make_aware(datetime(2026, 8, 10, 15, 0), zone),
        )

    def test_search_has_full_page_fallback(self):
        response = self.client.get(
            reverse("agenda:busqueda"),
            {"q": "planificación"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "agenda/busqueda.html")
        self.assertContains(response, "Preparar planificación")

    def test_ajax_search_returns_modal_html(self):
        response = self.client.get(
            reverse("agenda:busqueda"),
            {"q": "reunión"},
            **AJAX_HEADERS,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("Buscar en BFGenda", payload["html"])
        self.assertIn("Reunión de coordinación", payload["html"])

    def test_partial_search_returns_only_results_component(self):
        response = self.client.get(
            reverse("agenda:busqueda"),
            {
                "q": "trabajo",
                "partial": "resultados",
            },
            **AJAX_HEADERS,
        )

        self.assertEqual(response.status_code, 200)
        html = response.json()["html"]
        self.assertIn("global-search-results", html)
        self.assertIn("Trabajo docente", html)
        self.assertNotIn("id=\"app-modal-title\"", html)

    def test_search_never_exposes_another_users_items(self):
        response = self.client.get(
            reverse("agenda:busqueda"),
            {"q": "planificación"},
            **AJAX_HEADERS,
        )
        html = response.json()["html"]

        self.assertIn("Preparar planificación", html)
        self.assertNotIn("Planificación privada ajena", html)

    def test_search_can_filter_by_result_type(self):
        response = self.client.get(
            reverse("agenda:busqueda"),
            {
                "q": "trabajo",
                "tipo": "categorias",
            },
            **AJAX_HEADERS,
        )
        html = response.json()["html"]

        self.assertIn("Trabajo docente", html)
        self.assertNotIn("Preparar planificación", html)

    def test_search_matches_event_location(self):
        response = self.client.get(
            reverse("agenda:busqueda"),
            {"q": "CeRP"},
            **AJAX_HEADERS,
        )

        self.assertIn("Reunión de coordinación", response.json()["html"])

    def test_short_search_does_not_query_results(self):
        response = self.client.get(
            reverse("agenda:busqueda"),
            {"q": "a"},
            **AJAX_HEADERS,
        )
        html = response.json()["html"]

        self.assertIn("Escribe al menos 2 caracteres", html)
        self.assertNotIn("Preparar planificación", html)

    def test_search_result_urls_open_management_sections(self):
        response = self.client.get(
            reverse("agenda:busqueda"),
            {"q": "planificación"},
            **AJAX_HEADERS,
        )
        html = response.json()["html"]

        self.assertIn(reverse("agenda:tareas_listado"), html)
        self.assertIn(f"#tarea-{self.task.id}", html)

        event_response = self.client.get(
            reverse("agenda:busqueda"),
            {"q": "coordinación"},
            **AJAX_HEADERS,
        )
        event_html = event_response.json()["html"]

        self.assertIn(reverse("agenda:eventos_listado"), event_html)
        self.assertIn(f"#evento-{self.event.id}", event_html)

class ResponsivePhaseATests(TestCase):
    # Comprueba la estructura móvil introducida en la Fase A.

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="BrunoGuglielmone",
            password="clave-segura",
            first_name="Bruno",
            last_name="Guglielmone",
        )
        self.client.force_login(self.user)

    def test_mobile_header_shows_human_name_and_secure_logout(self):
        response = self.client.get(reverse("agenda:inicio"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="mobile-app-header"')
        self.assertContains(response, "Bruno Guglielmone")
        self.assertContains(response, 'class="mobile-logout-form"')
        self.assertContains(
            response,
            f'action="{reverse("agenda:cerrar_sesion")}"',
        )
        self.assertContains(response, 'type="submit"')
        self.assertContains(response, 'aria-label="Cerrar sesión"')

    def test_mobile_header_exposes_search_categories_and_settings(self):
        response = self.client.get(reverse("agenda:inicio"))

        self.assertContains(response, "data-global-search-trigger")
        self.assertContains(
            response,
            reverse("agenda:categorias_listado"),
        )
        self.assertContains(
            response,
            reverse("agenda:configuracion"),
        )
        self.assertContains(response, 'class="mobile-more-menu"')

    def test_mobile_quick_create_offers_tasks_and_events(self):
        response = self.client.get(reverse("agenda:inicio"))

        self.assertContains(response, 'class="mobile-quick-create"')
        self.assertContains(
            response,
            reverse("agenda:tarea_crear"),
        )
        self.assertContains(
            response,
            reverse("agenda:evento_crear"),
        )
        self.assertContains(response, "Nueva tarea")
        self.assertContains(response, "Nuevo evento")

    def test_task_and_event_filter_strips_remain_accessible(self):
        task_response = self.client.get(
            reverse("agenda:tareas_listado")
        )
        event_response = self.client.get(
            reverse("agenda:eventos_listado"),
            {"filtro": "todos"},
        )

        self.assertContains(
            task_response,
            'aria-label="Filtros de tareas"',
        )
        self.assertContains(
            event_response,
            'aria-label="Filtros de eventos"',
        )

    def test_primary_navigation_is_prepared_for_partial_updates(self):
        response = self.client.get(reverse("agenda:inicio"))
        html = response.content.decode()

        self.assertIn('class="mobile-brand-link"', html)
        self.assertGreaterEqual(html.count("data-app-link"), 15)
        self.assertRegex(
            html,
            r"/static/agenda/js/calendario(?:\.[0-9a-f]+)?\.js",
        )

    def test_task_and_event_filters_use_partial_navigation(self):
        task_response = self.client.get(reverse("agenda:tareas_listado"))
        event_response = self.client.get(
            reverse("agenda:eventos_listado"),
            {"filtro": "todos"},
        )

        task_html = task_response.content.decode()
        event_html = event_response.content.decode()

        self.assertIn("data-page-style", task_html)
        self.assertIn("data-page-style", event_html)
        self.assertGreaterEqual(task_html.count("data-app-link"), 23)
        self.assertGreaterEqual(event_html.count("data-app-link"), 21)

    def test_task_and_event_lists_enable_mobile_swipe_navigation(self):
        task_response = self.client.get(reverse("agenda:tareas_listado"))
        event_response = self.client.get(
            reverse("agenda:eventos_listado"),
            {"filtro": "todos"},
        )

        for response in (task_response, event_response):
            self.assertContains(response, "data-filter-swipe")
            self.assertContains(response, "data-filter-swipe-surface")
            self.assertContains(
                response,
                "Desliza el listado para cambiar de sección",
            )

    def test_mobile_swipe_assets_keep_vertical_scrolling_accessible(self):
        from pathlib import Path

        static_root = Path(__file__).resolve().parent / "static" / "agenda"
        script = (static_root / "js" / "app.js").read_text(encoding="utf-8")
        styles = (static_root / "css" / "inicio.css").read_text(
            encoding="utf-8"
        )

        self.assertIn('"touchstart"', script)
        self.assertIn('"touchend"', script)
        self.assertIn("Math.abs(deltaX) < 64", script)
        self.assertIn("filter-swipe-out-${direction}", script)
        self.assertIn("touch-action: pan-y", styles)
        self.assertIn("filter-swipe-enter-next", styles)

    def test_mobile_bottom_navigation_uses_consistent_vector_icons(self):
        response = self.client.get(reverse("agenda:inicio"))
        html = response.content.decode()
        mobile_navigation = html.split(
            'class="mobile-navigation"',
            maxsplit=1,
        )[1]

        self.assertGreaterEqual(mobile_navigation.count("<svg"), 4)
        self.assertIn('viewBox="0 0 24 24"', mobile_navigation)

    def test_calendar_and_settings_mark_their_page_styles(self):
        calendar_response = self.client.get(reverse("agenda:calendario"))
        settings_response = self.client.get(reverse("agenda:configuracion"))

        self.assertContains(calendar_response, "data-page-style")
        self.assertContains(settings_response, "data-page-style")


class CalendarResponsivePhaseTests(TestCase):
    """Cobertura estructural del calendario compacto para móvil."""

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="usuario-calendario-responsive",
            password="clave-segura",
        )
        self.client.force_login(self.user)

    def test_month_items_keep_accessible_names_in_compact_view(self):
        selected_day = timezone.localdate()
        Tarea.objects.create(
            usuario=self.user,
            titulo="Preparar calendario accesible",
            fecha_limite=selected_day,
            hora_limite=time(9, 30),
        )

        response = self.client.get(
            reverse("agenda:calendario"),
            {
                "vista": "mes",
                "mes": selected_day.strftime("%Y-%m"),
                "dia": selected_day.isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            (
                'aria-label="Tarea: Preparar calendario accesible, '
                '09:30"'
            ),
        )

    def test_calendar_loads_versioned_responsive_assets(self):
        response = self.client.get(reverse("agenda:calendario"))
        html = response.content.decode()
        static_root = Path(__file__).resolve().parent / "static" / "agenda"
        styles = (static_root / "css" / "calendario.css").read_text(
            encoding="utf-8"
        )
        script = (static_root / "js" / "calendario.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("agenda/css/calendario", html)
        self.assertIn("?v=20261105-3", html)
        self.assertIn("agenda/js/calendario", html)
        self.assertIn("?v=20260821-1", html)
        self.assertIn(".month-calendar {\n        min-width: 0;", styles)
        self.assertIn("scroll-snap-type: x proximity;", styles)
        self.assertIn(".selected-day-actions > * {", styles)
        self.assertIn("flex: 1 1 calc(50% - 5px);", styles)
        self.assertNotIn("text-transform: capitalize;", styles)
        self.assertIn("function revealSelectedWeekDay()", script)
        self.assertIn('"agende:content-updated"', script)
        self.assertIn("scroller.scrollTo({", script)


class VisualPhaseA2Tests(TestCase):
    # Pruebas visuales y estructurales de la Fase A2.

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="usuario-fase-a2",
            password="clave-segura",
        )
        self.client.force_login(self.user)

    def test_dashboard_shows_category_color_markers(self):
        category = Categoria.objects.create(
            usuario=self.user,
            nombre="Trabajo docente",
            color="#2E7D32",
        )
        today = timezone.localdate()
        tomorrow = today + timedelta(days=1)
        zone = timezone.get_current_timezone()

        Tarea.objects.create(
            usuario=self.user,
            categoria=category,
            titulo="Preparar clase",
            fecha_limite=today,
        )
        Evento.objects.create(
            usuario=self.user,
            categoria=category,
            titulo="Reunión próxima",
            inicio=timezone.make_aware(
                datetime.combine(tomorrow, time(9, 0)),
                zone,
            ),
            fin=timezone.make_aware(
                datetime.combine(tomorrow, time(10, 0)),
                zone,
            ),
        )

        response = self.client.get(reverse("agenda:inicio"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'class="metadata-category"',
            count=2,
        )
        self.assertContains(
            response,
            'class="metadata-category-dot"',
            count=2,
        )
        self.assertContains(
            response,
            'style="--metadata-category-color: #2E7D32;"',
            count=2,
        )
        self.assertContains(response, "Trabajo docente", count=2)
        self.assertContains(response, "Preparar clase")
        self.assertContains(response, "Reunión próxima")

    def test_category_selector_exposes_visual_colors(self):
        category = Categoria.objects.create(
            usuario=self.user,
            nombre="Estudio",
            color="#6A4CE0",
        )

        response = self.client.get(
            reverse("agenda:tarea_crear"),
            **AJAX_HEADERS,
        )
        html = response.json()["html"]

        self.assertIn("data-category-select", html)
        self.assertIn("data-category-select-preview", html)
        self.assertIn('data-category-select-input', html)
        self.assertIn('data-category-color="#6A4CE0"', html)
        self.assertIn('data-category-color="#9A9EAD"', html)
        self.assertIn(f'value="{category.id}"', html)

    def test_event_full_page_form_loads_category_selector_assets(self):
        Categoria.objects.create(
            usuario=self.user,
            nombre="Personal",
            color="#D94F70",
        )

        response = self.client.get(reverse("agenda:evento_crear"))
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("category-select", html)
        self.assertRegex(
            html,
            r"/static/agenda/css/category-select(?:\.[0-9a-f]+)?\.css",
        )
        self.assertRegex(
            html,
            r"/static/agenda/js/category-select(?:\.[0-9a-f]+)?\.js",
        )
        self.assertIn('data-category-color="#D94F70"', html)

    def test_category_selector_never_exposes_another_users_colors(self):
        other_user = get_user_model().objects.create_user(
            username="otro-usuario-fase-a2",
            password="otra-clave",
        )
        Categoria.objects.create(
            usuario=other_user,
            nombre="Privada",
            color="#123ABC",
        )

        response = self.client.get(
            reverse("agenda:tarea_crear"),
            **AJAX_HEADERS,
        )
        html = response.json()["html"]

        self.assertNotIn("Privada", html)
        self.assertNotIn("#123ABC", html)


    def test_modal_visual_polish_assets_and_css(self):
        from pathlib import Path

        response = self.client.get(reverse("agenda:inicio"))
        html = response.content.decode()
        css_path = (
            Path(__file__).resolve().parent
            / "static"
            / "agenda"
            / "css"
            / "modal.css"
        )
        css = css_path.read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("?v=20261105-3", html)
        self.assertIn("backdrop-filter: blur(4px);", css)
        self.assertIn("@keyframes modal-shell-enter", css)
        self.assertIn("@keyframes modal-backdrop-enter", css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)
        self.assertNotIn("--text-primary", css)


    def test_mobile_modal_does_not_force_virtual_keyboard(self):
        from pathlib import Path

        task_response = self.client.get(
            reverse("agenda:tarea_crear"),
            **AJAX_HEADERS,
        )
        event_response = self.client.get(
            reverse("agenda:evento_crear"),
            **AJAX_HEADERS,
        )
        task_html = task_response.json()["html"]
        event_html = event_response.json()["html"]

        app_path = (
            Path(__file__).resolve().parent
            / "static"
            / "agenda"
            / "js"
            / "app.js"
        )
        forms_path = Path(__file__).resolve().parent / "forms.py"
        full_form_path = (
            Path(__file__).resolve().parent
            / "templates"
            / "agenda"
            / "formulario.html"
        )

        app_source = app_path.read_text(encoding="utf-8")
        forms_source = forms_path.read_text(encoding="utf-8")
        full_form_source = full_form_path.read_text(encoding="utf-8")

        self.assertIn('data-autofocus="true"', task_html)
        self.assertIn('data-autofocus="true"', event_html)
        self.assertNotIn(" autofocus", task_html)
        self.assertNotIn(" autofocus", event_html)
        self.assertEqual(
            forms_source.count('"data-autofocus": "true"'),
            3,
        )
        self.assertNotIn('"autofocus": True', forms_source)
        self.assertIn(
            "(hover: hover) and (pointer: fine)",
            app_source,
        )
        self.assertIn("window.innerWidth > 760", app_source)
        self.assertIn("[data-autofocus]", app_source)
        self.assertIn("window.innerWidth <= 760", full_form_source)

        page_response = self.client.get(reverse("agenda:inicio"))
        self.assertContains(page_response, "?v=20261105-2")


    def test_loaded_modal_content_animates_and_mobile_layout_is_compact(self):
        from pathlib import Path

        app_path = (
            Path(__file__).resolve().parent
            / "static"
            / "agenda"
            / "js"
            / "app.js"
        )
        css_path = (
            Path(__file__).resolve().parent
            / "static"
            / "agenda"
            / "css"
            / "modal.css"
        )

        app_source = app_path.read_text(encoding="utf-8")
        css = css_path.read_text(encoding="utf-8")

        self.assertIn("function animateLoadedModalContent()", app_source)
        self.assertEqual(
            app_source.count("animateLoadedModalContent();"),
            2,
        )
        self.assertIn("modal-content-entering", app_source)
        self.assertIn("@keyframes modal-content-enter", css)
        self.assertIn(
            ".app-modal-content.modal-content-entering",
            css,
        )
        self.assertIn("width: calc(100vw - 30px);", css)
        self.assertIn("max-height: calc(100dvh - 42px);", css)
        self.assertIn("min-height: 72px;", css)
        self.assertIn("min-height: 44px;", css)

        response = self.client.get(reverse("agenda:inicio"))
        html = response.content.decode()

        self.assertRegex(
            html,
            r"/static/agenda/css/modal(?:\.[0-9a-f]{12})?\.css"
            r"\?v=20261105-3",
        )
        self.assertRegex(
            html,
            r"/static/agenda/js/app(?:\.[0-9a-f]{12})?\.js"
            r"\?v=20261105-2",
        )
        self.assertGreaterEqual(html.count("?v=20261105-3"), 3)
        self.assertEqual(html.count("?v=20261105-2"), 1)


    def test_mobile_form_rows_use_two_columns(self):
        from pathlib import Path

        css_path = (
            Path(__file__).resolve().parent
            / "static"
            / "agenda"
            / "css"
            / "modal.css"
        )
        css = css_path.read_text(encoding="utf-8")

        self.assertIn(
            "grid-template-columns: repeat(2, minmax(0, 1fr));",
            css,
        )
        self.assertIn(
            ".modal-form .form-row > :only-child",
            css,
        )
        self.assertIn("grid-column: 1 / -1;", css)
        self.assertIn("@media (max-width: 280px)", css)
        self.assertIn(
            '.modal-form input[type="datetime-local"]',
            css,
        )
        self.assertIn("@media (max-width: 360px)", css)
        self.assertIn("font-size: 0.68rem;", css)
        self.assertNotIn("@media (max-width: 340px)", css)

        response = self.client.get(reverse("agenda:inicio"))
        self.assertContains(response, "?v=20261105-3")

    def test_dashboard_uses_neutral_marker_without_category(self):
        Tarea.objects.create(
            usuario=self.user,
            titulo="Tarea sin clasificar",
            fecha_limite=timezone.localdate(),
        )

        response = self.client.get(reverse("agenda:inicio"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'style="--metadata-category-color: #9A9EAD;"',
        )
        self.assertContains(response, "Sin categoría")

    def test_authenticated_pages_load_the_saved_interface_theme(self):
        preferences = PreferenciasUsuario.objects.create(
            usuario=self.user,
            tema_interfaz=PreferenciasUsuario.TemaInterfaz.OSCURO,
        )

        response = self.client.get(reverse("agenda:inicio"))
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["tema_interfaz_preferencia"],
            preferences.tema_interfaz,
        )
        self.assertIn('data-theme-preference="oscuro"', html)
        self.assertIn('data-theme-authenticated="true"', html)
        self.assertIn("agenda/css/theme", html)
        self.assertIn("?v=20261105-1", html)
        self.assertIn("agenda/js/theme", html)

    def test_theme_assets_define_both_requested_palettes(self):
        from pathlib import Path

        static_root = Path(__file__).resolve().parent / "static" / "agenda"
        css = (static_root / "css" / "theme.css").read_text(encoding="utf-8")
        script = (static_root / "js" / "theme.js").read_text(encoding="utf-8")

        for color in (
            "#e7dff7",
            "#c6b4ee",
            "#a48ae0",
            "#7b5fd1",
            "#4e2fb0",
            "#05060e",
            "#12163a",
            "#2e1a63",
            "#5b2a86",
            "#b14aed",
        ):
            self.assertIn(color, css)

        self.assertIn('html[data-theme="dark"]', css)
        self.assertIn("prefers-color-scheme: dark", script)
        self.assertIn("bfgenda-theme-preference", script)
        self.assertIn("BFGendaTheme", script)

    def test_selectable_cards_keep_readable_theme_aware_states(self):
        from pathlib import Path

        css_root = Path(__file__).resolve().parent / "static" / "agenda" / "css"
        interactive_styles = {
            name: (css_root / name).read_text(encoding="utf-8")
            for name in (
                "inicio.css",
                "busqueda.css",
                "tareas.css",
                "eventos.css",
                "categorias.css",
                "modal.css",
            )
        }

        for css in interactive_styles.values():
            self.assertNotIn("#fbfaff", css)
            self.assertNotIn("#faf9ff", css)

        dashboard_css = interactive_styles["inicio.css"]
        self.assertIn(".statistic-button:active", dashboard_css)
        self.assertIn(".event-statistic-button:active", dashboard_css)
        self.assertIn("background: var(--primary-soft);", dashboard_css)

        modal_css = interactive_styles["modal.css"]
        self.assertIn(".summary-task-item:focus-visible", modal_css)
        self.assertIn(".summary-task-item:active", modal_css)

    def test_login_and_offline_shell_load_theme_assets(self):
        self.client.logout()

        login_response = self.client.get(reverse("login"))
        offline_response = self.client.get(reverse("pwa_offline"))

        self.assertContains(login_response, 'data-theme-authenticated="false"')
        self.assertContains(login_response, "agenda/css/theme")
        self.assertContains(login_response, "agenda/js/theme")
        self.assertContains(offline_response, "agenda/css/theme")
        self.assertContains(offline_response, "agenda/js/theme")
        self.assertNotContains(offline_response, "Tailscale")

    def test_service_worker_precaches_theme_foundation(self):
        response = self.client.get(reverse("pwa_service_worker"))
        source = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn('CACHE_VERSION = "bfgenda-public-v4"', source)
        self.assertIn("agenda/css/theme", source)
        self.assertIn("agenda/js/theme", source)
