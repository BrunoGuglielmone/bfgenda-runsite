"""Pruebas de la interfaz inicial de notificaciones."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from agenda.models import ConfiguracionAutomatizacion


class NotificationInterfaceTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="notificaciones",
            password="clave-segura-123",
        )
        self.client.force_login(self.user)

    def test_configuration_contains_notification_panel(self):
        response = self.client.get(
            reverse("agenda:configuracion")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "data-notification-panel",
        )

    def test_configuration_shows_scheduler_health(self):
        ConfiguracionAutomatizacion.objects.create(
            endpoint_url=(
                "https://bfgenda.onrender.com/"
                "sistema/recordatorios/despachar/"
            ),
            dispatch_token="token-privado",
            ultimo_estado="correcto",
        )

        response = self.client.get(reverse("agenda:configuracion"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Recordatorios en segundo plano")
        self.assertContains(
            response,
            "La automatización está configurada",
        )
        self.assertContains(
            response,
            "Activar notificaciones",
        )
        self.assertContains(
            response,
            "Enviar prueba",
        )
        self.assertContains(
            response,
            "agenda/js/notificaciones",
        )

    def test_service_worker_handles_notification_click(self):
        response = self.client.get(
            reverse("pwa_service_worker")
        )
        script = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            'self.addEventListener("notificationclick"',
            script,
        )
        self.assertIn("clients.openWindow", script)
        self.assertIn("event.notification.close()", script)

    def test_notification_script_requires_user_action(self):
        script_path = (
            "agenda/static/agenda/js/notificaciones.js"
        )

        with open(script_path, encoding="utf-8") as file:
            script = file.read()

        self.assertIn(
            'enableButton.addEventListener("click"',
            script,
        )
        self.assertIn(
            "Notification.requestPermission()",
            script,
        )
        self.assertNotIn(
            'DOMContentLoaded", Notification.requestPermission',
            script,
        )

    def test_hidden_notification_buttons_are_really_hidden(self):
        css_path = (
            "agenda/static/agenda/css/configuracion.css"
        )

        with open(css_path, encoding="utf-8") as file:
            css = file.read()

        self.assertIn(
            ".notification-primary-button[hidden]",
            css,
        )
        self.assertIn(
            ".notification-secondary-button[hidden]",
            css,
        )
        self.assertIn(
            "display: none !important;",
            css,
        )

    def test_notification_messages_use_safe_unicode(self):
        script_path = (
            "agenda/static/agenda/js/notificaciones.js"
        )

        with open(script_path, encoding="utf-8") as file:
            script = file.read()

        self.assertIn(
            r"Notificaci\u00f3n de prueba enviada.",
            script,
        )
        self.assertIn(
            r"notificaci\u00f3n",
            script,
        )

    def test_notification_script_checks_reminder_endpoint(self):
        script_path = (
            "agenda/static/agenda/js/notificaciones.js"
        )

        with open(script_path, encoding="utf-8") as file:
            script = file.read()

        self.assertIn("checkPendingReminders", script)
        self.assertIn("dataset.remindersUrl", script)
        self.assertIn("credentials: \"same-origin\"", script)
        self.assertIn("cache: \"no-store\"", script)
        self.assertIn("CHECK_INTERVAL_MS", script)

    def test_notification_script_avoids_local_duplicates(self):
        script_path = (
            "agenda/static/agenda/js/notificaciones.js"
        )

        with open(script_path, encoding="utf-8") as file:
            script = file.read()

        self.assertIn("window.localStorage.getItem", script)
        self.assertIn("window.localStorage.setItem", script)
        self.assertIn("reminder.tag", script)

    def test_base_contains_global_reminder_configuration(self):
        response = self.client.get(reverse("agenda:inicio"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "data-reminders-url=",
        )
        self.assertContains(
            response,
            "data-notification-icon=",
        )
        self.assertContains(
            response,
            "agenda/js/notificaciones",
        )

    def test_notification_script_uses_service_worker(self):
        script_path = (
            "agenda/static/agenda/js/notificaciones.js"
        )

        with open(script_path, encoding="utf-8") as file:
            script = file.read()

        self.assertIn(
            "registration.showNotification",
            script,
        )
        self.assertIn(
            '"bfgenda-prueba"',
            script,
        )
