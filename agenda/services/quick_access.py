"""Validación y protección del PIN utilizado en la pantalla pública."""

from __future__ import annotations

from hashlib import sha256

from django.contrib.auth import get_user_model
from django.core.cache import cache

from agenda.models import AccesoRapidoUsuario


MAX_FAILED_ATTEMPTS = 5
LOCK_SECONDS = 5 * 60


def _client_address(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")

    if forwarded:
        return forwarded.split(",", maxsplit=1)[0].strip()

    return request.META.get("REMOTE_ADDR", "unknown")


def _attempt_key(request, username: str) -> str:
    identity = f"{_client_address(request)}|{username.strip().casefold()}"
    digest = sha256(identity.encode("utf-8")).hexdigest()
    return f"bfgenda:quick-access:{digest}"


def authenticate_quick_access(request, *, username: str, pin: str):
    """Devuelve usuario y error público sin revelar qué credencial falló."""

    attempt_key = _attempt_key(request, username)
    failed_attempts = int(cache.get(attempt_key, 0) or 0)

    if failed_attempts >= MAX_FAILED_ATTEMPTS:
        return None, (
            "Se alcanzó el límite de intentos. Espera cinco minutos "
            "antes de volver a probar."
        )

    user_model = get_user_model()
    user = (
        user_model.objects
        .filter(username__iexact=username.strip(), is_active=True)
        .first()
    )
    quick_access = None

    if user is not None:
        quick_access = (
            AccesoRapidoUsuario.objects
            .filter(usuario=user)
            .first()
        )

    if quick_access is not None and quick_access.check_pin(pin):
        cache.delete(attempt_key)
        return user, None

    cache.set(attempt_key, failed_attempts + 1, timeout=LOCK_SECONDS)
    return None, (
        "El usuario o el PIN no son correctos, o el acceso rápido todavía "
        "no fue configurado."
    )


def set_user_pin(user, raw_pin: str) -> AccesoRapidoUsuario:
    quick_access, _ = AccesoRapidoUsuario.objects.get_or_create(usuario=user)
    quick_access.set_pin(raw_pin)
    quick_access.save()
    return quick_access
