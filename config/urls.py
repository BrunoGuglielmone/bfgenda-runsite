from django.contrib import admin
from django.urls import include, path

from agenda.views.pwa import manifest, offline, service_worker
from agenda.views.system import AgendeLoginView


urlpatterns = [
    # Recursos publicos necesarios para la instalacion PWA.
    path(
        "manifest.webmanifest",
        manifest,
        name="pwa_manifest",
    ),
    path(
        "service-worker.js",
        service_worker,
        name="pwa_service_worker",
    ),
    path(
        "sin-conexion/",
        offline,
        name="pwa_offline",
    ),

    path("admin/", admin.site.urls),

    # Acceso privado personalizado de BFGenda.
    path(
        "cuenta/login/",
        AgendeLoginView.as_view(),
        name="login",
    ),

    # Aplicación principal.
    path("", include("agenda.urls")),
]
