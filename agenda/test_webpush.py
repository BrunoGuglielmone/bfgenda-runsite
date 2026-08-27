"""Pruebas de suscripciones y envíos Web Push."""

from datetime import datetime, time
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from agenda.models import (
    EntregaNotificacion,
    SuscripcionPush,
    Tarea,
)
from agenda.services.webpush import (
    dispatch_due_push_notifications,
    send_test_push,
)


PUSH_SETTINGS = {
    "AGENDE_VAPID_PUBLIC_KEY": "B" + "a" * 86,
    "AGENDE_VAPID_PRIVATE_KEY": "clave-privada-de-prueba",
    "AGENDE_VAPID_SUBJECT": "mailto:pruebas@example.com",
}


def subscription_payload(endpoint="https://push.example.com/device/123"):
    return {
        "endpoint": endpoint,
        "expirationTime": None,
        "keys": {
            "p256dh": "A" * 87,
            "auth": "B" * 22,
        },
    }


def aware_local(year, month, day, hour, minute=0):
    return timezone.make_aware(
        datetime(year, month, day, hour, minute),
        timezone.get_current_timezone(),
    )


@override_settings(**PUSH_SETTINGS)
class PushSubscriptionEndpointTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="push-user",
            password="clave-segura-123",
        )
        self.client.force_login(self.user)

    def test_subscription_requires_post(self):
        response = self.client.get(
            reverse("agenda:suscripcion_push_guardar")
        )

        self.assertEqual(response.status_code, 405)

    def test_subscription_is_registered_for_authenticated_user(self):
        response = self.client.post(
            reverse("agenda:suscripcion_push_guardar"),
            data=subscription_payload(),
            content_type="application/json",
            HTTP_USER_AGENT="Chrome Android",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        subscription = SuscripcionPush.objects.get()
        self.assertEqual(subscription.usuario, self.user)
        self.assertEqual(subscription.agente_usuario, "Chrome Android")
        self.assertTrue(subscription.activa)

    def test_subscription_rejects_non_https_endpoint(self):
        response = self.client.post(
            reverse("agenda:suscripcion_push_guardar"),
            data=subscription_payload("http://push.example.com/device/123"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.assertFalse(SuscripcionPush.objects.exists())

    def test_only_owner_can_disable_subscription(self):
        subscription = SuscripcionPush.objects.create(
            usuario=self.user,
            endpoint="https://push.example.com/device/private",
            clave_p256dh="A" * 87,
            clave_auth="B" * 22,
        )
        other_user = get_user_model().objects.create_user(
            username="other-push-user",
            password="clave-segura-456",
        )
        self.client.force_login(other_user)

        response = self.client.post(
            reverse("agenda:suscripcion_push_eliminar"),
            data={"endpoint": subscription.endpoint},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        subscription.refresh_from_db()
        self.assertTrue(subscription.activa)

    @patch("agenda.services.webpush.webpush")
    def test_server_test_uses_registered_subscription(self, mocked_webpush):
        subscription = SuscripcionPush.objects.create(
            usuario=self.user,
            endpoint="https://push.example.com/device/test",
            clave_p256dh="A" * 87,
            clave_auth="B" * 22,
        )

        response = self.client.post(
            reverse("agenda:suscripcion_push_probar"),
            data={"endpoint": subscription.endpoint},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        mocked_webpush.assert_called_once()
        subscription.refresh_from_db()
        self.assertIsNotNone(subscription.ultimo_envio_correcto_en)


@override_settings(**PUSH_SETTINGS)
class PushDispatchTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="push-dispatch",
            password="clave-segura-123",
        )
        self.subscription = SuscripcionPush.objects.create(
            usuario=self.user,
            endpoint="https://push.example.com/device/dispatch",
            clave_p256dh="A" * 87,
            clave_auth="B" * 22,
        )
        Tarea.objects.create(
            usuario=self.user,
            titulo="Aviso desde el servidor",
            fecha_limite=datetime(2026, 8, 26).date(),
            hora_limite=time(18, 0),
        )

    @patch("agenda.services.webpush.webpush")
    def test_dispatch_sends_once_per_subscription_and_tag(
        self,
        mocked_webpush,
    ):
        now = aware_local(2026, 8, 26, 17, 45)

        first = dispatch_due_push_notifications(now=now)
        second = dispatch_due_push_notifications(now=now)

        self.assertEqual(first.sent, 1)
        self.assertEqual(second.sent, 0)
        self.assertEqual(second.skipped, 1)
        mocked_webpush.assert_called_once()
        delivery = EntregaNotificacion.objects.get()
        self.assertIsNotNone(delivery.entregada_en)
        self.assertEqual(delivery.intentos, 1)

    @patch("agenda.services.webpush.webpush")
    def test_test_payload_uses_vapid_and_timeout(self, mocked_webpush):
        send_test_push(self.subscription)

        kwargs = mocked_webpush.call_args.kwargs
        self.assertEqual(kwargs["ttl"], 3600)
        self.assertEqual(kwargs["timeout"], 10)
        self.assertEqual(
            kwargs["vapid_claims"],
            {"sub": "mailto:pruebas@example.com"},
        )


class PushFrontendTests(TestCase):
    def test_service_worker_handles_background_push(self):
        response = self.client.get(reverse("pwa_service_worker"))
        script = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn('self.addEventListener("push"', script)
        self.assertIn("event.data.json()", script)
        self.assertIn("self.registration.showNotification", script)

    def test_notification_script_registers_push_subscription(self):
        with open(
            "agenda/static/agenda/js/notificaciones.js",
            encoding="utf-8",
        ) as script_file:
            script = script_file.read()

        self.assertIn("registration.pushManager.subscribe", script)
        self.assertIn("applicationServerKey", script)
        self.assertIn('getCookie("csrftoken")', script)
        self.assertIn("data-notification-disable", script)


class HostedPushSchedulerTests(TestCase):
    @override_settings(AGENDE_PUSH_SCHEDULER_ENABLED=False)
    @patch("scripts.servidor_agende.threading.Thread")
    def test_scheduler_stays_disabled_locally(self, mocked_thread):
        from scripts.servidor_agende import start_push_scheduler

        self.assertTrue(start_push_scheduler())
        mocked_thread.assert_not_called()

    @override_settings(
        AGENDE_PUSH_SCHEDULER_ENABLED=True,
        AGENDE_VAPID_PUBLIC_KEY="",
        AGENDE_VAPID_PRIVATE_KEY="",
    )
    def test_scheduler_rejects_missing_vapid_configuration(self):
        from scripts.servidor_agende import start_push_scheduler

        self.assertFalse(start_push_scheduler())

    @override_settings(
        AGENDE_PUSH_SCHEDULER_ENABLED=True,
        **PUSH_SETTINGS,
    )
    @patch("scripts.servidor_agende.atexit.register")
    @patch("scripts.servidor_agende.threading.Thread")
    def test_scheduler_starts_one_daemon_thread(
        self,
        mocked_thread,
        mocked_atexit,
    ):
        from scripts.servidor_agende import (
            PUSH_SCHEDULER_STOP,
            start_push_scheduler,
        )

        self.assertTrue(start_push_scheduler())
        mocked_thread.assert_called_once_with(
            target=mocked_thread.call_args.kwargs["target"],
            name="bfgenda-web-push",
            daemon=True,
        )
        mocked_thread.return_value.start.assert_called_once_with()
        mocked_atexit.assert_called_once_with(PUSH_SCHEDULER_STOP.set)

    @override_settings(AGENDE_PUSH_SCHEDULER_INTERVAL_SECONDS=60)
    @patch("scripts.servidor_agende.close_old_connections")
    @patch("scripts.servidor_agende.dispatch_due_push_notifications")
    @patch("scripts.servidor_agende.ensure_daily_backup")
    @patch("scripts.servidor_agende.PUSH_SCHEDULER_STOP")
    def test_scheduler_checks_backup_and_push_in_same_cycle(
        self,
        mocked_stop,
        mocked_backup,
        mocked_dispatch,
        mocked_close_connections,
    ):
        from scripts.servidor_agende import run_push_scheduler

        mocked_stop.is_set.side_effect = [False, True]
        mocked_backup.return_value = None
        mocked_dispatch.return_value = MagicMock(
            sent=0,
            failed=0,
            deactivated=0,
        )

        run_push_scheduler()

        mocked_backup.assert_called_once_with()
        mocked_dispatch.assert_called_once_with()
        mocked_stop.wait.assert_called_once_with(60)
        self.assertEqual(mocked_close_connections.call_count, 2)
