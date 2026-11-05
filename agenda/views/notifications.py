"""Endpoints privados para las notificaciones de BFGenda."""

from __future__ import annotations

import json
import logging
import re
import secrets
from urllib.parse import urlsplit

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from agenda.models import ConfiguracionAutomatizacion, SuscripcionPush
from agenda.services.notifications import collect_due_reminders
from agenda.services.webpush import (
    PushConfigurationError,
    PushDeliveryError,
    dispatch_due_push_notifications,
    push_is_configured,
    send_test_push,
)


MAX_JSON_BODY_BYTES = 16 * 1024
MAX_ENDPOINT_LENGTH = 4096
BASE64URL_PATTERN = re.compile(r"^[A-Za-z0-9_-]+={0,2}$")
LOGGER = logging.getLogger("agenda")


def _guardar_estado_automatizacion(
    automation,
    *,
    estado,
    error="",
    result=None,
    success=False,
):
    now = timezone.now()
    automation.ultima_ejecucion_en = now
    automation.ultimo_estado = estado
    automation.ultimo_error = error[:500]
    update_fields = [
        "ultima_ejecucion_en",
        "ultimo_estado",
        "ultimo_error",
        "actualizada_en",
    ]

    if result is not None:
        automation.ultimo_enviados = result.sent
        automation.ultimo_fallidos = result.failed
        automation.ultimo_omitidos = result.skipped
        update_fields.extend(
            [
                "ultimo_enviados",
                "ultimo_fallidos",
                "ultimo_omitidos",
            ]
        )

    if success:
        automation.ultimo_exito_en = now
        update_fields.append("ultimo_exito_en")

    automation.save(update_fields=update_fields)


@csrf_exempt
@require_POST
def despachar_recordatorios_programados(request):
    """Permite que Neon active el despacho sin exponer datos personales."""

    authorization = request.headers.get("Authorization", "")
    prefix = "Bearer "
    supplied_token = (
        authorization[len(prefix):].strip()
        if authorization.startswith(prefix)
        else ""
    )
    automation = (
        ConfiguracionAutomatizacion.objects
        .filter(activa=True)
        .order_by("id")
        .first()
    )

    if (
        automation is None
        or not supplied_token
        or not secrets.compare_digest(
            supplied_token,
            automation.dispatch_token,
        )
    ):
        return JsonResponse({"detail": "No autorizado."}, status=403)

    try:
        result = dispatch_due_push_notifications()
    except PushConfigurationError as error:
        _guardar_estado_automatizacion(
            automation,
            estado="error",
            error=str(error),
        )
        return JsonResponse({"detail": str(error)}, status=503)
    except Exception:
        LOGGER.exception("Falló el despachador programado de Web Push.")
        _guardar_estado_automatizacion(
            automation,
            estado="error",
            error="Error interno durante el despacho.",
        )
        return JsonResponse(
            {"detail": "No fue posible completar el despacho."},
            status=500,
        )

    _guardar_estado_automatizacion(
        automation,
        estado="correcto",
        result=result,
        success=True,
    )

    return JsonResponse(
        {
            "sent": result.sent,
            "failed": result.failed,
            "skipped": result.skipped,
            "deactivated": result.deactivated,
        }
    )


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
