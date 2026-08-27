"""Vistas de autenticación y control local del servidor."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from ..services.shutdown import (
    can_shutdown,
    clear_shutdown_access,
    grant_shutdown_access,
    schedule_shutdown,
)


class AgendeLoginView(LoginView):
    """Inicio de sesión con acceso temporal al apagado tras cerrar sesión."""

    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["puede_detener_agende"] = can_shutdown(self.request)
        return context

    def form_valid(self, form):
        clear_shutdown_access(self.request)
        return super().form_valid(form)


@login_required
@require_POST
def cerrar_sesion(request):
    """Cierra la sesión y habilita brevemente el apagado en el login."""

    was_superuser = bool(request.user.is_superuser)
    logout(request)
    grant_shutdown_access(
        request,
        was_superuser=was_superuser,
    )
    return redirect("login")


@require_GET
@never_cache
def estado_agende(request):
    """Confirma que el servidor sigue respondiendo.

    La pantalla de apagado consulta este punto mientras Waitress continúa
    activo. Cuando el proceso se detiene, la petición deja de responder y el
    navegador puede informar que BFGenda ya quedó cerrado.
    """

    return JsonResponse(
        {
            "activo": True,
        }
    )


@require_POST
def detener_agende(request):
    """Programa el apagado solo con una autorización temporal válida."""

    if not can_shutdown(request):
        clear_shutdown_access(request)
        messages.error(
            request,
            (
                "La opción para detener BFGenda ya no está disponible. "
                "Inicia sesión y ciérrala nuevamente desde la aplicación."
            ),
        )
        return redirect("login")

    if not schedule_shutdown():
        messages.error(
            request,
            (
                "No se pudo iniciar el apagado. Comprueba los registros "
                "o utiliza el acceso directo Detener BFGenda."
            ),
        )
        return redirect("login")

    clear_shutdown_access(request)

    return render(
        request,
        "registration/apagando.html",
        status=202,
    )
