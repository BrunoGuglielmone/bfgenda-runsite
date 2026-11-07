from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from agenda.models import AccesoRapidoUsuario, Evento, Tarea
from agenda.services.quick_access import set_user_pin


AJAX_HEADERS = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


class QuickAccessTests(TestCase):
    def setUp(self):
        cache.clear()
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="bruno-rapido",
            password="Clave-segura-2026",
        )
        self.login_url = reverse("login")

    def tearDown(self):
        cache.clear()

    def configure_pin(self, pin="4826"):
        return set_user_pin(self.user, pin)

    def test_pin_is_hashed_and_can_be_configured_from_settings(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("agenda:configuracion_pin"),
            {
                "current_password": "Clave-segura-2026",
                "pin": "4826",
                "pin_confirmation": "4826",
                "return_url": reverse("agenda:configuracion"),
            },
            **AJAX_HEADERS,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        quick_access = AccesoRapidoUsuario.objects.get(usuario=self.user)
        self.assertNotEqual(quick_access.pin_hash, "4826")
        self.assertTrue(quick_access.check_pin("4826"))
        self.assertFalse(quick_access.check_pin("0000"))

    def test_settings_reject_wrong_account_password(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("agenda:configuracion_pin"),
            {
                "current_password": "incorrecta",
                "pin": "4826",
                "pin_confirmation": "4826",
            },
            **AJAX_HEADERS,
        )

        self.assertEqual(response.status_code, 422)
        self.assertFalse(AccesoRapidoUsuario.objects.exists())
        self.assertIn("contraseña actual no es correcta", response.json()["html"])

    def test_login_exposes_quick_task_event_and_recovery_panels(self):
        response = self.client.get(self.login_url)
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn('data-login-panel-target="tarea"', html)
        self.assertIn('data-login-panel-target="evento"', html)
        self.assertIn('data-login-panel="recuperar"', html)
        self.assertIn('name="tarea-pin"', html)
        self.assertIn('name="evento-pin"', html)
        self.assertIn("¿Olvidaste tu PIN?", html)

    def test_quick_task_is_created_without_starting_session(self):
        self.configure_pin()
        response = self.client.post(
            self.login_url,
            {
                "login_action": "quick_task",
                "tarea-username": self.user.username,
                "tarea-pin": "4826",
                "tarea-titulo": "Tarea desde el acceso rápido",
                "tarea-fecha_limite": "2026-11-07",
                "tarea-hora_limite": "09:30",
            },
        )

        self.assertRedirects(response, f"{self.login_url}?panel=tarea")
        task = Tarea.objects.get(usuario=self.user)
        self.assertEqual(task.titulo, "Tarea desde el acceso rápido")
        self.assertEqual(task.hora_limite.strftime("%H:%M"), "09:30")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_quick_event_uses_requested_duration(self):
        self.configure_pin()
        response = self.client.post(
            self.login_url,
            {
                "login_action": "quick_event",
                "evento-username": self.user.username,
                "evento-pin": "4826",
                "evento-titulo": "Evento desde el acceso rápido",
                "evento-inicio": "2026-11-07T10:00",
                "evento-duracion_minutos": "90",
            },
        )

        self.assertRedirects(response, f"{self.login_url}?panel=evento")
        event = Evento.objects.get(usuario=self.user)
        self.assertEqual(event.fin - event.inicio, timedelta(minutes=90))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_wrong_pin_does_not_create_data_and_is_rate_limited(self):
        self.configure_pin()
        payload = {
            "login_action": "quick_task",
            "tarea-username": self.user.username,
            "tarea-pin": "0000",
            "tarea-titulo": "No debe guardarse",
        }

        for _ in range(5):
            response = self.client.post(self.login_url, payload)
            self.assertEqual(response.status_code, 200)

        blocked = self.client.post(self.login_url, payload)

        self.assertFalse(Tarea.objects.exists())
        self.assertContains(blocked, "límite de intentos")

    def test_pin_can_be_recovered_with_account_password(self):
        quick_access = self.configure_pin("4826")
        response = self.client.post(
            self.login_url,
            {
                "login_action": "recover_pin",
                "recuperar-username": self.user.username,
                "recuperar-password": "Clave-segura-2026",
                "recuperar-pin": "7351",
                "recuperar-pin_confirmation": "7351",
            },
        )

        self.assertRedirects(response, f"{self.login_url}?panel=tarea")
        quick_access.refresh_from_db()
        self.assertTrue(quick_access.check_pin("7351"))
        self.assertFalse(quick_access.check_pin("4826"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_recovery_rejects_wrong_password(self):
        self.configure_pin("4826")
        response = self.client.post(
            self.login_url,
            {
                "login_action": "recover_pin",
                "recuperar-username": self.user.username,
                "recuperar-password": "incorrecta",
                "recuperar-pin": "7351",
                "recuperar-pin_confirmation": "7351",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "usuario o la contraseña no son correctos")
        quick_access = AccesoRapidoUsuario.objects.get(usuario=self.user)
        self.assertTrue(quick_access.check_pin("4826"))

    def test_event_initial_value_is_in_the_future(self):
        response = self.client.get(f"{self.login_url}?panel=evento")
        initial = response.context["quick_event_form"]["inicio"].value()
        parsed = datetime.strptime(initial, "%Y-%m-%dT%H:%M")
        aware = timezone.make_aware(parsed, timezone.get_current_timezone())

        self.assertGreater(aware, timezone.now())
