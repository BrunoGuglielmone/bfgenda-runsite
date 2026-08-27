from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.templatetags.static import static
from django.urls import reverse

from .services.shutdown import SESSION_KEY


class ShutdownFlowTests(TestCase):
    """Comprueba que el apagado solo aparezca tras cerrar sesión localmente."""

    def setUp(self):
        user_model = get_user_model()
        self.superuser = user_model.objects.create_superuser(
            username="bruno",
            email="bruno@example.com",
            password="clave-segura",
        )
        self.regular_user = user_model.objects.create_user(
            username="usuario",
            password="otra-clave",
        )
        self.local_desktop = {
            "REMOTE_ADDR": "127.0.0.1",
            "HTTP_HOST": "127.0.0.1:8000",
            "HTTP_USER_AGENT": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/140.0 Safari/537.36"
            ),
            "HTTP_SEC_CH_UA_MOBILE": "?0",
        }

    def test_initial_login_does_not_offer_shutdown(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Detener BFGenda")

    def test_login_avoids_native_autofocus_on_mobile(self):
        response = self.client.get(reverse("login"))
        html = response.content.decode()
        static_root = Path(__file__).resolve().parent / "static" / "agenda"
        login_script = (static_root / "js" / "login.js").read_text(
            encoding="utf-8"
        )
        login_styles = (static_root / "css" / "login.css").read_text(
            encoding="utf-8"
        )

        self.assertIn('data-autofocus="true"', html)
        self.assertNotIn(" autofocus", html)
        self.assertIn("agenda/js/login", html)
        self.assertIn("?v=20260821-1", html)
        self.assertIn("(hover: hover) and (pointer: fine)", login_script)
        self.assertIn("window.innerWidth > 760", login_script)
        self.assertIn("@media (max-width: 760px)", login_styles)
        self.assertIn("[data-desktop-shutdown]", login_styles)

    def test_status_endpoint_reports_active_server_without_cache(self):
        response = self.client.get(
            reverse("agenda:estado_agende")
        )

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content,
            {
                "activo": True,
            },
        )
        self.assertIn(
            "no-store",
            response.headers.get("Cache-Control", ""),
        )

    @patch(
        "agenda.services.shutdown.managed_server_is_running",
        return_value=True,
    )
    def test_superuser_logout_enables_shutdown_temporarily(self, _running):
        self.client.force_login(self.superuser)

        response = self.client.post(
            reverse("agenda:cerrar_sesion"),
            **self.local_desktop,
        )

        self.assertRedirects(response, reverse("login"))

        login_response = self.client.get(
            reverse("login"),
            **self.local_desktop,
        )

        self.assertContains(login_response, "Detener BFGenda")
        self.assertContains(
            login_response,
            "data-desktop-shutdown",
            count=2,
        )
        self.assertIn(SESSION_KEY, self.client.session)

    @patch(
        "agenda.services.shutdown.managed_server_is_running",
        return_value=True,
    )
    def test_regular_user_logout_does_not_enable_shutdown(self, _running):
        self.client.force_login(self.regular_user)

        self.client.post(
            reverse("agenda:cerrar_sesion"),
            **self.local_desktop,
        )

        login_response = self.client.get(
            reverse("login"),
            **self.local_desktop,
        )

        self.assertNotContains(login_response, "Detener BFGenda")

    @patch(
        "agenda.services.shutdown.managed_server_is_running",
        return_value=True,
    )
    def test_remote_logout_does_not_enable_shutdown(self, _running):
        self.client.force_login(self.superuser)

        self.client.post(
            reverse("agenda:cerrar_sesion"),
            REMOTE_ADDR="192.168.1.80",
        )

        login_response = self.client.get(
            reverse("login"),
            REMOTE_ADDR="192.168.1.80",
        )

        self.assertNotContains(login_response, "Detener BFGenda")

    @patch(
        "agenda.services.shutdown.managed_server_is_running",
        return_value=True,
    )
    @override_settings(
        ALLOWED_HOSTS=[
            "testserver",
            "127.0.0.1",
            "desktop-fajsuce.example.ts.net",
        ]
    )
    def test_tailscale_proxy_cannot_enable_shutdown(self, _running):
        self.client.force_login(self.superuser)
        remote_request = {
            **self.local_desktop,
            "HTTP_HOST": "desktop-fajsuce.example.ts.net",
            "HTTP_TAILSCALE_USER_LOGIN": "bruno@example.com",
        }

        self.client.post(
            reverse("agenda:cerrar_sesion"),
            **remote_request,
        )

        login_response = self.client.get(
            reverse("login"),
            **remote_request,
        )

        self.assertNotContains(login_response, "Detener BFGenda")
        self.assertNotIn(SESSION_KEY, self.client.session)

    @patch(
        "agenda.services.shutdown.managed_server_is_running",
        return_value=True,
    )
    @override_settings(
        ALLOWED_HOSTS=[
            "testserver",
            "127.0.0.1",
            "desktop-fajsuce.example.ts.net",
        ]
    )
    def test_proxy_host_without_identity_cannot_enable_shutdown(self, _running):
        self.client.force_login(self.superuser)
        proxy_request = {
            **self.local_desktop,
            "HTTP_HOST": "desktop-fajsuce.example.ts.net",
        }

        self.client.post(
            reverse("agenda:cerrar_sesion"),
            **proxy_request,
        )

        login_response = self.client.get(
            reverse("login"),
            **proxy_request,
        )

        self.assertNotContains(login_response, "Detener BFGenda")
        self.assertNotIn(SESSION_KEY, self.client.session)

    @patch(
        "agenda.services.shutdown.managed_server_is_running",
        return_value=True,
    )
    def test_mobile_loopback_request_cannot_enable_shutdown(self, _running):
        self.client.force_login(self.superuser)
        mobile_request = {
            **self.local_desktop,
            "HTTP_USER_AGENT": (
                "Mozilla/5.0 (Linux; Android 16; Pixel 9) Mobile"
            ),
            "HTTP_SEC_CH_UA_MOBILE": "?1",
        }

        self.client.post(
            reverse("agenda:cerrar_sesion"),
            **mobile_request,
        )

        login_response = self.client.get(
            reverse("login"),
            **mobile_request,
        )

        self.assertNotContains(login_response, "Detener BFGenda")
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_direct_shutdown_post_is_rejected(self):
        response = self.client.post(
            reverse("agenda:detener_agende"),
            **self.local_desktop,
        )

        self.assertRedirects(response, reverse("login"))

    @patch("agenda.views.system.schedule_shutdown", return_value=True)
    @patch(
        "agenda.services.shutdown.managed_server_is_running",
        return_value=True,
    )
    def test_authorized_shutdown_returns_status_page(
        self,
        _running,
        schedule_mock,
    ):
        self.client.force_login(self.superuser)
        self.client.post(
            reverse("agenda:cerrar_sesion"),
            **self.local_desktop,
        )

        response = self.client.post(
            reverse("agenda:detener_agende"),
            **self.local_desktop,
        )

        self.assertEqual(response.status_code, 202)
        self.assertContains(
            response,
            "BFGenda se está deteniendo",
            status_code=202,
        )
        self.assertContains(
            response,
            reverse("agenda:estado_agende"),
            status_code=202,
        )
        self.assertContains(
            response,
            static("agenda/js/apagado.js"),
            status_code=202,
        )
        schedule_mock.assert_called_once_with()
        self.assertNotIn(SESSION_KEY, self.client.session)

    @patch(
        "agenda.services.shutdown.managed_server_is_running",
        return_value=True,
    )
    def test_logging_in_consumes_shutdown_permission(self, _running):
        self.client.force_login(self.superuser)
        self.client.post(
            reverse("agenda:cerrar_sesion"),
            **self.local_desktop,
        )

        response = self.client.post(
            reverse("login"),
            {
                "username": "bruno",
                "password": "clave-segura",
            },
            **self.local_desktop,
        )

        self.assertRedirects(response, reverse("agenda:inicio"))
        self.assertNotIn(SESSION_KEY, self.client.session)
