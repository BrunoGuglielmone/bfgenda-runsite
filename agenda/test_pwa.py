"""Pruebas de los recursos publicos de la PWA."""

from __future__ import annotations

import json

from django.test import SimpleTestCase
from django.urls import reverse


class PwaEndpointTests(SimpleTestCase):
    def test_manifest_is_public_and_valid(self):
        response = self.client.get(reverse("pwa_manifest"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response["Content-Type"].startswith(
                "application/manifest+json"
            )
        )

        manifest = json.loads(response.content.decode("utf-8"))

        self.assertEqual(manifest["id"], "/")
        self.assertEqual(manifest["name"], "BFGenda")
        self.assertEqual(manifest["short_name"], "BFGenda")
        self.assertEqual(manifest["start_url"], "/")
        self.assertEqual(manifest["scope"], "/")
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(len(manifest["icons"]), 2)

    def test_manifest_icons_have_required_sizes(self):
        response = self.client.get(reverse("pwa_manifest"))
        manifest = json.loads(response.content.decode("utf-8"))

        sizes = {
            icon["sizes"]
            for icon in manifest["icons"]
        }

        self.assertIn("192x192", sizes)
        self.assertIn("512x512", sizes)

        for icon in manifest["icons"]:
            self.assertTrue(icon["src"].startswith("/static/"))
            self.assertEqual(icon["type"], "image/png")

    def test_service_worker_is_public_javascript(self):
        response = self.client.get(reverse("pwa_service_worker"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response["Content-Type"].startswith(
                "application/javascript"
            )
        )
        self.assertEqual(
            response["Service-Worker-Allowed"],
            "/",
        )

    def test_service_worker_is_not_cached_by_http(self):
        response = self.client.get(reverse("pwa_service_worker"))

        cache_control = response["Cache-Control"]

        self.assertIn("no-cache", cache_control)
        self.assertIn("no-store", cache_control)

    def test_service_worker_does_not_cache_private_pages(self):
        response = self.client.get(reverse("pwa_service_worker"))
        script = response.content.decode("utf-8")

        self.assertIn(
            'if (request.method !== "GET")',
            script,
        )
        self.assertIn(
            'request.mode === "navigate"',
            script,
        )
        self.assertIn(
            'url.pathname.startsWith("/static/")',
            script,
        )

        self.assertNotIn('"/tareas/"', script)
        self.assertNotIn('"/eventos/"', script)
        self.assertNotIn('"/configuracion/"', script)
        self.assertNotIn('"/buscar/"', script)

    def test_offline_page_can_be_precached(self):
        response = self.client.get(reverse("pwa_offline"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response["Content-Type"].startswith("text/html")
        )
        self.assertContains(response, "Sin conexi&oacute;n")
        self.assertContains(response, "Volver a intentar")
        self.assertContains(
            response,
            "bfgenda-simbolo-xl-192",
        )
        self.assertNotContains(
            response,
            "bfgenda-simbolo-xl-128",
        )

    def test_offline_icon_is_precached(self):
        worker_response = self.client.get(
            reverse("pwa_service_worker")
        )
        offline_response = self.client.get(
            reverse("pwa_offline")
        )

        worker = worker_response.content.decode("utf-8")
        offline = offline_response.content.decode("utf-8")

        self.assertIn(
            "bfgenda-simbolo-xl-192",
            worker,
        )
        self.assertIn(
            "bfgenda-simbolo-xl-192",
            offline,
        )

    def test_main_page_links_manifest(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 302)

        login_response = self.client.get(response.url)

        self.assertEqual(login_response.status_code, 200)
        self.assertContains(
            login_response,
            'rel="manifest"',
        )
        self.assertContains(
            login_response,
            reverse("pwa_manifest"),
        )
        self.assertContains(
            login_response,
            "agenda/js/pwa",
        )
