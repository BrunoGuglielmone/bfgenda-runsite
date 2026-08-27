from dataclasses import dataclass, field
from typing import Any

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.utils.http import url_has_allowed_host_and_scheme


@dataclass(frozen=True)
class FormViewConfig:
    """Datos de presentación compartidos por formularios completos y modales."""

    eyebrow: str
    title: str
    description: str
    icon: str
    submit_label: str
    cancel_url: str
    hidden_fields: tuple[dict[str, str], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ConfirmationViewConfig:
    """Datos reutilizables para confirmar una acción irreversible."""

    eyebrow: str
    title: str
    description: str
    icon: str
    confirm_label: str
    cancel_url: str
    action_url: str
    warning: str = "Esta acción no se puede deshacer."
    details: tuple[str, ...] = field(default_factory=tuple)
    hidden_fields: tuple[dict[str, str], ...] = field(default_factory=tuple)


def is_ajax(request) -> bool:
    """Indica si la petición fue iniciada por el cliente JavaScript de BFGenda."""

    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def get_return_url(request, fallback: str) -> str:
    """Obtiene una URL de retorno segura y limitada al mismo host."""

    candidate = request.POST.get("return_url") or request.GET.get("return_url")

    if not candidate:
        return fallback

    if url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate

    return fallback


def build_form_rows(form) -> list[list[Any]]:
    """Convierte el diseño declarado por el formulario en filas de BoundField."""

    layout = getattr(form, "layout", tuple((name,) for name in form.fields))
    return [[form[field_name] for field_name in row] for row in layout]


def form_context(form, config: FormViewConfig) -> dict[str, Any]:
    """Construye el contexto único usado por la página y el modal."""

    return {
        "formulario": form,
        "filas_formulario": build_form_rows(form),
        "form_config": config,
        "form_is_multipart": form.is_multipart(),
    }


def modal_content_response(
    request,
    *,
    template_name: str,
    context: dict[str, Any],
    fallback_url: str,
):
    """Devuelve contenido HTML para el modal o redirige sin JavaScript."""

    if not is_ajax(request):
        return redirect(fallback_url)

    html = render_to_string(
        template_name,
        context,
        request=request,
    )
    return JsonResponse({"ok": True, "html": html})


def form_response(
    request,
    form,
    config: FormViewConfig,
    *,
    invalid: bool = False,
):
    """Renderiza el mismo formulario como modal AJAX o como página completa."""

    context = form_context(form, config)
    context["form_action"] = request.path

    if is_ajax(request):
        html = render_to_string(
            "agenda/modales/formulario_modal.html",
            context,
            request=request,
        )
        return JsonResponse(
            {"ok": not invalid, "html": html},
            status=422 if invalid else 200,
        )

    return render(
        request,
        "agenda/formulario.html",
        context,
    )


def confirmation_response(request, config: ConfirmationViewConfig):
    """Muestra una confirmación reutilizable como modal o página completa."""

    context = {"confirmation": config}

    if is_ajax(request):
        html = render_to_string(
            "agenda/modales/confirmacion_modal.html",
            context,
            request=request,
        )
        return JsonResponse({"ok": True, "html": html})

    return render(
        request,
        "agenda/confirmacion.html",
        context,
    )


def saved_response(
    request,
    *,
    message: str,
    redirect_url: str,
    date_value=None,
    created: bool = False,
):
    """Devuelve JSON para una actualización dinámica o una redirección normal."""

    if is_ajax(request):
        payload = {
            "ok": True,
            "message": message,
            "refresh_url": redirect_url,
            "history_url": redirect_url,
        }

        if date_value is not None:
            payload["date"] = date_value.isoformat()

        return JsonResponse(payload, status=201 if created else 200)

    return redirect(redirect_url)
