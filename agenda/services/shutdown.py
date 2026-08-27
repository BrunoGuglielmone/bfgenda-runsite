"""Control seguro del apagado local de BFGenda.

La autorización se concede únicamente después de cerrar sesión desde la
interfaz de BFGenda, dura unos minutos y se guarda en la nueva sesión anónima.
El servidor solo puede apagarse desde el mismo equipo que lo ejecuta.

El apagado solicitado desde la web se ejecuta dentro del propio proceso de
BFGenda. Esto evita depender de que Windows consiga iniciar un segundo proceso
de PowerShell oculto desde Waitress.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import threading
import time

from django.conf import settings

from config.env import local_ipv4_addresses


LOGGER = logging.getLogger("agenda.shutdown")
SESSION_KEY = "agende_shutdown_allowed_until"
LOOPBACK_ADDRESSES = {"127.0.0.1", "::1"}
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
TAILSCALE_IDENTITY_HEADERS = (
    "HTTP_TAILSCALE_USER_LOGIN",
    "HTTP_TAILSCALE_USER_NAME",
    "HTTP_TAILSCALE_USER_PROFILE_PIC",
)
MOBILE_USER_AGENT_MARKERS = (
    "android",
    "iphone",
    "ipad",
    "ipod",
    "mobile",
    "windows phone",
)

_SHUTDOWN_LOCK = threading.Lock()
_SHUTDOWN_SCHEDULED = False


def _pid_file_path() -> Path:
    """Devuelve la ruta del PID utilizado por el lanzador estable."""

    return Path(settings.BASE_DIR) / "runtime" / "agende.pid"


def managed_server_is_running() -> bool:
    """Indica si BFGenda fue iniciado mediante el lanzador estable."""

    pid_file = _pid_file_path()

    if not pid_file.is_file():
        return False

    try:
        stored_pid = int(
            pid_file.read_text(encoding="utf-8-sig").strip()
        )
    except (OSError, TypeError, ValueError):
        return False

    return stored_pid == os.getpid()


def request_is_mobile(request) -> bool:
    """Detecta navegadores móviles para excluir el control de apagado."""

    mobile_hint = str(
        request.META.get("HTTP_SEC_CH_UA_MOBILE", "")
    ).strip().lower()

    if mobile_hint in {"?1", "1", "true"}:
        return True

    user_agent = str(
        request.META.get("HTTP_USER_AGENT", "")
    ).strip().lower()
    return any(marker in user_agent for marker in MOBILE_USER_AGENT_MARKERS)


def request_uses_tailscale_serve(request) -> bool:
    """Reconoce peticiones que Tailscale Serve envió al backend local."""

    return any(
        str(request.META.get(header, "")).strip()
        for header in TAILSCALE_IDENTITY_HEADERS
    )


def _request_host(request) -> str:
    """Obtiene el nombre del host solicitado sin conservar el puerto."""

    host = request.get_host().strip().lower()

    if host.startswith("[") and "]" in host:
        return host[1:].split("]", 1)[0]

    if host.count(":") == 1:
        return host.rsplit(":", 1)[0]

    return host


def request_is_local(request) -> bool:
    """Comprueba que la petición sea local, directa y no móvil."""

    if request_is_mobile(request) or request_uses_tailscale_serve(request):
        return False

    remote_address = str(request.META.get("REMOTE_ADDR", "")).strip()

    if not remote_address:
        return False

    remote_address = remote_address.split("%", 1)[0]
    allowed_addresses = LOOPBACK_ADDRESSES | set(local_ipv4_addresses())
    allowed_hosts = LOOPBACK_HOSTS | set(local_ipv4_addresses())

    return (
        remote_address in allowed_addresses
        and _request_host(request) in allowed_hosts
    )


def clear_shutdown_access(request) -> None:
    """Elimina cualquier autorización temporal de apagado."""

    if SESSION_KEY in request.session:
        request.session.pop(SESSION_KEY, None)
        request.session.modified = True


def grant_shutdown_access(request, *, was_superuser: bool) -> bool:
    """Autoriza temporalmente el apagado tras un cierre de sesión válido."""

    clear_shutdown_access(request)

    if not getattr(settings, "AGENDE_WEB_SHUTDOWN_ENABLED", True):
        return False

    if not was_superuser:
        return False

    if not request_is_local(request):
        return False

    if not managed_server_is_running():
        return False

    duration = int(
        getattr(
            settings,
            "AGENDE_WEB_SHUTDOWN_WINDOW_SECONDS",
            600,
        )
    )

    request.session[SESSION_KEY] = int(time.time()) + max(duration, 60)
    request.session.modified = True
    return True


def can_shutdown(request) -> bool:
    """Valida la autorización temporal de la sesión anónima."""

    if request.user.is_authenticated:
        return False

    if not getattr(settings, "AGENDE_WEB_SHUTDOWN_ENABLED", True):
        return False

    if not request_is_local(request):
        clear_shutdown_access(request)
        return False

    if not managed_server_is_running():
        clear_shutdown_access(request)
        return False

    try:
        expires_at = int(request.session.get(SESSION_KEY, 0))
    except (TypeError, ValueError):
        expires_at = 0

    if expires_at <= int(time.time()):
        clear_shutdown_access(request)
        return False

    return True


def _remove_current_pid_file() -> None:
    """Elimina el PID únicamente cuando pertenece al proceso actual."""

    pid_file = _pid_file_path()

    try:
        if not pid_file.is_file():
            return

        stored_pid = pid_file.read_text(
            encoding="utf-8-sig",
        ).strip()

        if stored_pid == str(os.getpid()):
            pid_file.unlink(missing_ok=True)
    except OSError:
        LOGGER.exception(
            "No se pudo eliminar el archivo PID antes del apagado."
        )


def _terminate_current_process() -> None:
    """Finaliza el proceso completo después de limpiar sus recursos básicos.

    Esta función se ejecuta en un temporizador separado, cuando la respuesta
    HTTP de la pantalla de apagado ya tuvo tiempo de llegar al navegador.
    """

    LOGGER.info("Comenzando el apagado interno de BFGenda.")

    _remove_current_pid_file()

    try:
        # Fuerza el volcado y cierre de los manejadores de registro antes de
        # finalizar el proceso de forma inmediata.
        logging.shutdown()
    finally:
        # sys.exit() solo terminaría el hilo del temporizador. os._exit()
        # finaliza el proceso Waitress completo, que es el comportamiento
        # necesario para apagar BFGenda desde la propia aplicación.
        os._exit(0)


def schedule_shutdown() -> bool:
    """Programa el apagado interno de Waitress tras una breve espera."""

    global _SHUTDOWN_SCHEDULED

    delay_seconds = int(
        getattr(
            settings,
            "AGENDE_WEB_SHUTDOWN_DELAY_SECONDS",
            3,
        )
    )

    with _SHUTDOWN_LOCK:
        if _SHUTDOWN_SCHEDULED:
            return True

        try:
            timer = threading.Timer(
                interval=max(delay_seconds, 1),
                function=_terminate_current_process,
            )
            timer.daemon = True
            timer.start()
        except RuntimeError:
            LOGGER.exception(
                "No se pudo iniciar el temporizador de apagado."
            )
            return False

        _SHUTDOWN_SCHEDULED = True

    LOGGER.info(
        "Se programó el apagado interno de BFGenda dentro de %s segundos.",
        max(delay_seconds, 1),
    )
    return True
