"""Vistas de autenticación y control local del servidor."""

from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from ..forms_quick import (
    QuickEventForm,
    QuickPinRecoveryForm,
    QuickTaskForm,
)
from ..models import Evento, Tarea
from ..services.quick_access import authenticate_quick_access, set_user_pin
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
    quick_panels = {"login", "tarea", "evento", "recuperar"}

    @staticmethod
    def _event_initial():
        # Redondear hacia la próxima hora completa. Sumar solo 30 minutos y
        # truncar podía devolver una hora ya pasada durante la primera mitad
        # de cada hora.
        start = timezone.localtime() + timedelta(hours=1)
        start = start.replace(minute=0, second=0, microsecond=0)
        return {"inicio": start.strftime("%Y-%m-%dT%H:%M")}

    def get_context_data(self, **kwargs):
        quick_task_form = kwargs.pop("quick_task_form", None)
        quick_event_form = kwargs.pop("quick_event_form", None)
        pin_recovery_form = kwargs.pop("pin_recovery_form", None)
        requested_panel = kwargs.pop(
            "active_panel",
            self.request.GET.get("panel", "login"),
        )
        context = super().get_context_data(**kwargs)
        context["puede_detener_agende"] = can_shutdown(self.request)
        context["active_panel"] = (
            requested_panel if requested_panel in self.quick_panels else "login"
        )
        context["quick_task_form"] = quick_task_form or QuickTaskForm(
            prefix="tarea"
        )
        context["quick_event_form"] = quick_event_form or QuickEventForm(
            prefix="evento",
            initial=self._event_initial(),
        )
        context["pin_recovery_form"] = pin_recovery_form or QuickPinRecoveryForm(
            prefix="recuperar"
        )
        return context

    def _quick_form_response(self, *, panel, form, form_name):
        context_kwargs = {
            "form": self.get_form(),
            "active_panel": panel,
            form_name: form,
        }
        return self.render_to_response(self.get_context_data(**context_kwargs))

    def _create_quick_task(self):
        form = QuickTaskForm(self.request.POST, prefix="tarea")

        if not form.is_valid():
            return self._quick_form_response(
                panel="tarea",
                form=form,
                form_name="quick_task_form",
            )

        user, error = authenticate_quick_access(
            self.request,
            username=form.cleaned_data["username"],
            pin=form.cleaned_data["pin"],
        )

        if user is None:
            form.add_error(None, error)
            return self._quick_form_response(
                panel="tarea",
                form=form,
                form_name="quick_task_form",
            )

        task = Tarea.objects.create(
            usuario=user,
            titulo=form.cleaned_data["titulo"],
            fecha_limite=form.cleaned_data.get("fecha_limite"),
            hora_limite=form.cleaned_data.get("hora_limite"),
        )
        messages.success(
            self.request,
            f'La tarea “{task.titulo}” se agregó correctamente.',
        )
        return redirect(f"{reverse('login')}?panel=tarea")

    def _create_quick_event(self):
        form = QuickEventForm(self.request.POST, prefix="evento")

        if not form.is_valid():
            return self._quick_form_response(
                panel="evento",
                form=form,
                form_name="quick_event_form",
            )

        user, error = authenticate_quick_access(
            self.request,
            username=form.cleaned_data["username"],
            pin=form.cleaned_data["pin"],
        )

        if user is None:
            form.add_error(None, error)
            return self._quick_form_response(
                panel="evento",
                form=form,
                form_name="quick_event_form",
            )

        start = form.cleaned_data["inicio"]
        end = start + timedelta(
            minutes=form.cleaned_data["duracion_minutos"]
        )
        event = Evento.objects.create(
            usuario=user,
            titulo=form.cleaned_data["titulo"],
            inicio=start,
            fin=end,
        )
        messages.success(
            self.request,
            f'El evento “{event.titulo}” se agregó correctamente.',
        )
        return redirect(f"{reverse('login')}?panel=evento")

    def _recover_quick_pin(self):
        form = QuickPinRecoveryForm(self.request.POST, prefix="recuperar")

        if not form.is_valid():
            return self._quick_form_response(
                panel="recuperar",
                form=form,
                form_name="pin_recovery_form",
            )

        user = authenticate(
            self.request,
            username=form.cleaned_data["username"],
            password=form.cleaned_data["password"],
        )

        if user is None:
            form.add_error(None, "El usuario o la contraseña no son correctos.")
            return self._quick_form_response(
                panel="recuperar",
                form=form,
                form_name="pin_recovery_form",
            )

        set_user_pin(user, form.cleaned_data["pin"])
        messages.success(
            self.request,
            "El PIN fue reemplazado. Ya puedes utilizar el acceso rápido.",
        )
        return redirect(f"{reverse('login')}?panel=tarea")

    def post(self, request, *args, **kwargs):
        action = request.POST.get("login_action", "login")

        if action == "quick_task":
            return self._create_quick_task()

        if action == "quick_event":
            return self._create_quick_event()

        if action == "recover_pin":
            return self._recover_quick_pin()

        return super().post(request, *args, **kwargs)

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
