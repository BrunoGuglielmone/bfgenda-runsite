"""Envío servidor de notificaciones Web Push para BFGenda."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from py_vapid import VapidException
from pywebpush import WebPushException, webpush

from agenda.models import EntregaNotificacion, SuscripcionPush
from agenda.services.notifications import collect_due_reminders


LOGGER = logging.getLogger("agenda")
MAX_DELIVERY_ATTEMPTS = 3


class PushConfigurationError(RuntimeError):
    """La configuración VAPID necesaria no está disponible."""


class PushDeliveryError(RuntimeError):
    """El proveedor Push rechazó o no pudo procesar el mensaje."""


@dataclass
class DispatchResult:
    subscriptions: int = 0
    reminders: int = 0
    sent: int = 0
    skipped: int = 0
    failed: int = 0
    deactivated: int = 0


def push_is_configured() -> bool:
    """Indica si el host tiene las tres opciones VAPID necesarias."""

    return bool(
        settings.AGENDE_VAPID_PUBLIC_KEY
        and settings.AGENDE_VAPID_PRIVATE_KEY
        and settings.AGENDE_VAPID_SUBJECT
    )


def _require_push_configuration() -> None:
    if not push_is_configured():
        raise PushConfigurationError(
            "Web Push no está configurado en este servidor."
        )


def _subscription_info(subscription: SuscripcionPush) -> dict:
    return {
        "endpoint": subscription.endpoint,
        "keys": {
            "p256dh": subscription.clave_p256dh,
            "auth": subscription.clave_auth,
        },
    }


def _response_status(error: WebPushException) -> int | None:
    response = getattr(error, "response", None)
    return getattr(response, "status_code", None)


def send_push_payload(
    subscription: SuscripcionPush,
    payload: dict,
) -> None:
    """Envía un payload y desactiva endpoints expirados definitivamente."""

    _require_push_configuration()

    try:
        webpush(
            subscription_info=_subscription_info(subscription),
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=settings.AGENDE_VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.AGENDE_VAPID_SUBJECT},
            ttl=3600,
            timeout=10,
        )
    except VapidException as error:
        raise PushConfigurationError(
            "La identidad VAPID no es válida; debe configurarse como "
            "un contacto mailto:."
        ) from error
    except WebPushException as error:
        status = _response_status(error)

        if status in {404, 410}:
            subscription.activa = False
            subscription.save(update_fields=["activa", "actualizada_en"])

        raise PushDeliveryError(
            f"El proveedor Push devolvió {status or 'un error de conexión'}."
        ) from error


def test_push_payload() -> dict:
    return {
        "title": "BFGenda",
        "body": "Las notificaciones en segundo plano funcionan correctamente.",
        "tag": "bfgenda-prueba-servidor",
        "url": "/configuracion/",
    }


def send_test_push(subscription: SuscripcionPush) -> None:
    send_push_payload(subscription, test_push_payload())
    subscription.ultimo_envio_correcto_en = timezone.now()
    subscription.save(
        update_fields=["ultimo_envio_correcto_en", "actualizada_en"]
    )


def _record_attempt(delivery: EntregaNotificacion) -> None:
    delivery.intentos += 1
    delivery.ultimo_intento_en = timezone.now()
    delivery.ultimo_error = ""
    delivery.save(
        update_fields=[
            "intentos",
            "ultimo_intento_en",
            "ultimo_error",
        ]
    )


def _mark_delivery_success(
    delivery: EntregaNotificacion,
    subscription: SuscripcionPush,
) -> None:
    delivered_at = timezone.now()
    delivery.entregada_en = delivered_at
    delivery.ultimo_error = ""
    delivery.save(update_fields=["entregada_en", "ultimo_error"])
    subscription.ultimo_envio_correcto_en = delivered_at
    subscription.save(
        update_fields=["ultimo_envio_correcto_en", "actualizada_en"]
    )


def _mark_delivery_failure(
    delivery: EntregaNotificacion,
    error: PushDeliveryError,
) -> None:
    delivery.ultimo_error = str(error)[:500]
    delivery.save(update_fields=["ultimo_error"])


def dispatch_due_push_notifications(*, now=None, user=None) -> DispatchResult:
    """Envía recordatorios vencidos y evita duplicarlos entre ejecuciones."""

    _require_push_configuration()
    now = now or timezone.now()
    subscriptions = (
        SuscripcionPush.objects
        .filter(activa=True)
        .select_related("usuario")
        .order_by("usuario_id", "id")
    )

    if user is not None:
        subscriptions = subscriptions.filter(usuario=user)

    result = DispatchResult()

    for subscription in subscriptions:
        result.subscriptions += 1
        reminders = collect_due_reminders(subscription.usuario, now=now)
        result.reminders += len(reminders)

        for reminder in reminders:
            with transaction.atomic():
                delivery, _ = (
                    EntregaNotificacion.objects
                    .select_for_update()
                    .get_or_create(
                        suscripcion=subscription,
                        etiqueta=reminder["tag"],
                    )
                )

                if (
                    delivery.entregada_en is not None
                    or delivery.intentos >= MAX_DELIVERY_ATTEMPTS
                ):
                    result.skipped += 1
                    continue

                _record_attempt(delivery)

            payload = {
                "title": reminder["title"],
                "body": reminder["body"],
                "tag": reminder["tag"],
                "url": reminder["url"],
            }

            try:
                send_push_payload(subscription, payload)
            except PushDeliveryError as error:
                _mark_delivery_failure(delivery, error)
                result.failed += 1

                if not subscription.activa:
                    result.deactivated += 1
                    break

                LOGGER.warning(
                    "Falló Web Push para la suscripción %s: %s",
                    subscription.pk,
                    error,
                )
                continue

            _mark_delivery_success(delivery, subscription)
            result.sent += 1

    return result
