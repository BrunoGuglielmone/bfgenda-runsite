"""Endpoints privados para las notificaciones de BFGenda."""

from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from agenda.models import SuscripcionPush
from agenda.services.notifications import collect_due_reminders
from agenda.services.webpush import (
    PushConfigurationError,
    PushDeliveryError,
    push_is_configured,
    send_test_push,
)


MAX_JSON_BODY_BYTES = 16 * 1024
MAX_ENDPOINT_LENGTH = 4096
BASE64URL_PATTERN = re.compile(r"^[A-Za-z0-9_-]+={0,2}$")


def _no_store_json(payload, *, status=200):
    response = JsonResponse(payload, status=status)
    response["Cache-Control"] = "no-store"
    return response


def _read_json_body(request):
    if len(request.body) > MAX_JSON_BODY_BYTES:
        raise ValueError("La solicitud es demasiado grande.")

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("La solicitud JSON no es válida.") from error

    if not isinstance(payload, dict):
        raise ValueError("La solicitud JSON no es válida.")

    return payload


def _validated_subscription(payload):
    endpoint = payload.get("endpoint")
    keys = payload.get("keys")
    expiration_time = payload.get("expirationTime")

    if not isinstance(endpoint, str):
        raise ValueError("Falta el endpoint de la suscripción.")

    endpoint = endpoint.strip()
    parsed_endpoint = urlsplit(endpoint)

    if (
        not endpoint
        or len(endpoint) > MAX_ENDPOINT_LENGTH
        or parsed_endpoint.scheme != "https"
        or not parsed_endpoint.netloc
        or parsed_endpoint.username is not None
        or parsed_endpoint.password is not None
    ):
        raise ValueError("El endpoint de la suscripción no es válido.")

    if not isinstance(keys, dict):
        raise ValueError("Faltan las claves de la suscripción.")

    p256dh = keys.get("p256dh")
    auth = keys.get("auth")

    for value, label, minimum in (
        (p256dh, "p256dh", 32),
        (auth, "auth", 8),
    ):
        if (
            not isinstance(value, str)
            or not minimum <= len(value) <= 255
            or BASE64URL_PATTERN.fullmatch(value) is None
        ):
            raise ValueError(f"La clave {label} no es válida.")

    if expiration_time is not None:
        if (
            isinstance(expiration_time, bool)
            or not isinstance(expiration_time, int | float)
            or expiration_time < 0
        ):
            raise ValueError("La expiración de la suscripción no es válida.")
        expiration_time = int(expiration_time)

    return endpoint, p256dh, auth, expiration_time


@login_required
@require_GET
def recordatorios_pendientes(request):
    """Entrega recordatorios recientes del usuario autenticado."""

    reminders = collect_due_reminders(request.user)

    return _no_store_json(
        {
            "ok": True,
            "reminders": reminders,
            "count": len(reminders),
        },
    )


@login_required
@require_POST
def suscripcion_push_guardar(request):
    """Registra o renueva la suscripción Push del dispositivo actual."""

    if not push_is_configured():
        return _no_store_json(
            {
                "ok": False,
                "error": "Web Push aún no está configurado en el servidor.",
            },
            status=503,
        )

    try:
        payload = _read_json_body(request)
        endpoint, p256dh, auth, expiration_time = _validated_subscription(
            payload
        )
    except ValueError as error:
        return _no_store_json(
            {"ok": False, "error": str(error)},
            status=400,
        )

    subscription, created = SuscripcionPush.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            "usuario": request.user,
            "clave_p256dh": p256dh,
            "clave_auth": auth,
            "expiracion_milisegundos": expiration_time,
            "agente_usuario": request.headers.get("User-Agent", "")[:300],
            "activa": True,
        },
    )
    return _no_store_json(
        {
            "ok": True,
            "created": created,
            "subscription_id": subscription.pk,
        }
    )


@login_required
@require_POST
def suscripcion_push_eliminar(request):
    """Desactiva en el servidor el endpoint del dispositivo actual."""

    try:
        payload = _read_json_body(request)
    except ValueError as error:
        return _no_store_json(
            {"ok": False, "error": str(error)},
            status=400,
        )

    endpoint = payload.get("endpoint")

    if not isinstance(endpoint, str) or not endpoint.strip():
        return _no_store_json(
            {"ok": False, "error": "Falta el endpoint de la suscripción."},
            status=400,
        )

    updated = SuscripcionPush.objects.filter(
        usuario=request.user,
        endpoint=endpoint.strip(),
    ).update(activa=False)
    return _no_store_json({"ok": True, "updated": updated})


@login_required
@require_POST
def suscripcion_push_probar(request):
    """Envía una prueba real al proveedor Push del dispositivo."""

    try:
        payload = _read_json_body(request)
    except ValueError as error:
        return _no_store_json(
            {"ok": False, "error": str(error)},
            status=400,
        )

    endpoint = payload.get("endpoint")

    if not isinstance(endpoint, str) or not endpoint.strip():
        return _no_store_json(
            {"ok": False, "error": "Falta el endpoint de la suscripción."},
            status=400,
        )

    subscription = SuscripcionPush.objects.filter(
        usuario=request.user,
        endpoint=endpoint.strip(),
        activa=True,
    ).first()

    if subscription is None:
        return _no_store_json(
            {"ok": False, "error": "Este dispositivo no está registrado."},
            status=404,
        )

    try:
        send_test_push(subscription)
    except PushConfigurationError as error:
        return _no_store_json(
            {"ok": False, "error": str(error)},
            status=503,
        )
    except PushDeliveryError as error:
        return _no_store_json(
            {"ok": False, "error": str(error)},
            status=502,
        )

    return _no_store_json({"ok": True})
