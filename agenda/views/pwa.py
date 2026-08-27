"""Recursos publicos necesarios para instalar BFGenda como PWA."""

from __future__ import annotations

import json

from django.http import HttpResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@require_GET
def manifest(request):
    """Devuelve el manifiesto instalable de BFGenda."""

    payload = {
        "id": "/",
        "name": "BFGenda",
        "short_name": "BFGenda",
        "description": (
            "Agenda personal privada para organizar tareas y eventos."
        ),
        "lang": "es",
        "dir": "ltr",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "any",
        "background_color": "#171526",
        "theme_color": "#6657d9",
        "categories": [
            "productivity",
            "utilities",
        ],
        "icons": [
            {
                "src": static(
                    "agenda/img/branding/"
                    "bfgenda-simbolo-xl-192.png"
                ),
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable",
            },
            {
                "src": static(
                    "agenda/img/branding/"
                    "bfgenda-simbolo-xl-512.png"
                ),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable",
            },
        ],
    }

    response = HttpResponse(
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        content_type=(
            "application/manifest+json; charset=utf-8"
        ),
    )
    response["Cache-Control"] = "no-cache"
    return response


@never_cache
@require_GET
def service_worker(request):
    """Publica el service worker desde la raiz del sitio."""

    response = render(
        request,
        "pwa/service-worker.js",
        content_type="application/javascript; charset=utf-8",
    )
    response["Service-Worker-Allowed"] = "/"
    return response


@never_cache
@require_GET
def offline(request):
    """Muestra una pagina neutral cuando no hay conexion."""

    response = render(
        request,
        "pwa/offline.html",
        status=200,
    )
    response["Cache-Control"] = "no-cache"
    return response
