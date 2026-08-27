"""Pruebas del modo de mantenimiento de BFGenda."""

import threading
import time

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from agenda.middleware import MaintenanceMiddleware
from agenda.services.maintenance import (
    active_request_count,
    end_maintenance,
    leave_request,
    maintenance_is_active,
    maintenance_mode,
    try_enter_request,
)


class MaintenanceServiceTests(SimpleTestCase):
    def tearDown(self):
        if maintenance_is_active():
            end_maintenance()

    def test_context_manager_activates_and_releases_maintenance(self):
        self.assertFalse(maintenance_is_active())

        with maintenance_mode():
            self.assertTrue(maintenance_is_active())

        self.assertFalse(maintenance_is_active())

    def test_context_manager_releases_maintenance_after_error(self):
        with self.assertRaises(RuntimeError):
            with maintenance_mode():
                raise RuntimeError("fallo simulado")

        self.assertFalse(maintenance_is_active())

    def test_maintenance_waits_for_an_existing_request(self):
        request_started = threading.Event()
        release_request = threading.Event()
        maintenance_entered = threading.Event()

        def active_request():
            self.assertTrue(try_enter_request())
            request_started.set()

            try:
                release_request.wait(timeout=2)
            finally:
                leave_request()

        def start_maintenance():
            with maintenance_mode():
                maintenance_entered.set()

        request_thread = threading.Thread(
            target=active_request,
            daemon=True,
        )
        request_thread.start()

        self.assertTrue(request_started.wait(timeout=1))
        self.assertEqual(active_request_count(), 1)

        maintenance_thread = threading.Thread(
            target=start_maintenance,
            daemon=True,
        )
        maintenance_thread.start()

        timeout_at = time.monotonic() + 1

        while (
            not maintenance_is_active()
            and time.monotonic() < timeout_at
        ):
            time.sleep(0.01)

        self.assertTrue(maintenance_is_active())
        self.assertFalse(maintenance_entered.is_set())
        self.assertFalse(try_enter_request())

        release_request.set()

        request_thread.join(timeout=1)
        maintenance_thread.join(timeout=1)

        self.assertFalse(request_thread.is_alive())
        self.assertFalse(maintenance_thread.is_alive())
        self.assertTrue(maintenance_entered.is_set())
        self.assertFalse(maintenance_is_active())


class MaintenanceMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = MaintenanceMiddleware(
            lambda request: HttpResponse("disponible")
        )

    def tearDown(self):
        if maintenance_is_active():
            end_maintenance()

    def test_normal_request_continues(self):
        response = self.middleware(self.factory.get("/"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"disponible")

    def test_request_receives_503_during_maintenance(self):
        with maintenance_mode():
            response = self.middleware(self.factory.get("/"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response["Retry-After"], "3")
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertContains(
            response,
            "BFGenda se est",
            status_code=503,
        )
