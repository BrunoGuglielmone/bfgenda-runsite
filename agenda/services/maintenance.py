"""Coordinacion del modo de mantenimiento de BFGenda."""

from __future__ import annotations

import threading
from contextlib import contextmanager


_CONDITION = threading.Condition(threading.RLock())
_REQUEST_STATE = threading.local()
_ACTIVE_REQUESTS = 0
_MAINTENANCE_ACTIVE = False


def maintenance_is_active() -> bool:
    """Indica si BFGenda esta bloqueando nuevas solicitudes."""

    with _CONDITION:
        return _MAINTENANCE_ACTIVE


def active_request_count() -> int:
    """Devuelve la cantidad de solicitudes registradas."""

    with _CONDITION:
        return _ACTIVE_REQUESTS


def current_thread_has_request() -> bool:
    """Indica si el hilo actual esta procesando una solicitud."""

    return bool(
        getattr(_REQUEST_STATE, "request_active", False)
    )


def try_enter_request() -> bool:
    """
    Registra una solicitud normal.

    Devuelve False cuando una restauracion ya activo el mantenimiento.
    """

    global _ACTIVE_REQUESTS

    with _CONDITION:
        if _MAINTENANCE_ACTIVE:
            return False

        if current_thread_has_request():
            raise RuntimeError(
                "El hilo actual ya tiene una solicitud registrada."
            )

        _ACTIVE_REQUESTS += 1
        _REQUEST_STATE.request_active = True
        return True


def leave_request() -> None:
    """Libera una solicitud registrada por el middleware."""

    global _ACTIVE_REQUESTS

    with _CONDITION:
        if not current_thread_has_request():
            raise RuntimeError(
                "El hilo actual no tiene una solicitud registrada."
            )

        if _ACTIVE_REQUESTS <= 0:
            raise RuntimeError(
                "El contador de solicitudes de BFGenda es inconsistente."
            )

        _REQUEST_STATE.request_active = False
        _ACTIVE_REQUESTS -= 1
        _CONDITION.notify_all()


def begin_maintenance() -> None:
    """
    Bloquea solicitudes nuevas y drena las que siguen activas.

    Si el hilo actual pertenece a la solicitud que inicia una
    restauracion, esa solicitud se excluye automaticamente de la espera.
    """

    global _MAINTENANCE_ACTIVE

    own_request_count = 1 if current_thread_has_request() else 0

    with _CONDITION:
        if _MAINTENANCE_ACTIVE:
            raise RuntimeError(
                "BFGenda ya se encuentra en modo de mantenimiento."
            )

        _MAINTENANCE_ACTIVE = True

        while _ACTIVE_REQUESTS > own_request_count:
            _CONDITION.wait()


def end_maintenance() -> None:
    """Permite nuevamente el ingreso de solicitudes."""

    global _MAINTENANCE_ACTIVE

    with _CONDITION:
        _MAINTENANCE_ACTIVE = False
        _CONDITION.notify_all()


@contextmanager
def maintenance_mode():
    """Activa y desactiva el mantenimiento de manera segura."""

    begin_maintenance()

    try:
        yield
    finally:
        end_maintenance()
