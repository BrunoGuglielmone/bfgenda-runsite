"""Servidor estable de BFGenda basado en Waitress."""

from __future__ import annotations

import atexit
import logging
import os
import sys
import threading
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.env import env_int, load_env_file  # noqa: E402


load_env_file(BASE_DIR / ".env")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.conf import settings  # noqa: E402
from django.db import close_old_connections  # noqa: E402
from django.utils import timezone  # noqa: E402

from agenda.services.backups import ensure_daily_backup  # noqa: E402
from agenda.services.webpush import (  # noqa: E402
    dispatch_due_push_notifications,
    push_is_configured,
)
from config.wsgi import application  # noqa: E402
from waitress import serve  # noqa: E402


RUNTIME_DIR = BASE_DIR / "runtime"
PID_FILE = RUNTIME_DIR / "agende.pid"
LOGGER = logging.getLogger("waitress")
PUSH_LOGGER = logging.getLogger("agenda")
PUSH_SCHEDULER_STOP = threading.Event()


def service_port() -> int:
    """Respeta el puerto impuesto por el proveedor administrado."""

    return env_int("AGENDE_PORT", env_int("PORT", 8000))


def remove_pid_file() -> None:
    """Elimina el PID únicamente si pertenece a este proceso."""

    try:
        if not PID_FILE.exists():
            return

        stored_pid = PID_FILE.read_text(
            encoding="utf-8",
        ).strip()

        if stored_pid == str(os.getpid()):
            PID_FILE.unlink(missing_ok=True)
    except OSError:
        LOGGER.exception("No se pudo eliminar el archivo PID.")


def run_push_scheduler() -> None:
    """Despacha recordatorios periódicamente en la instancia única del host."""

    interval = settings.AGENDE_PUSH_SCHEDULER_INTERVAL_SECONDS
    PUSH_LOGGER.info(
        "Programador Web Push activo cada %s segundos.",
        interval,
    )
    last_backup_date = None

    while not PUSH_SCHEDULER_STOP.is_set():
        close_old_connections()

        try:
            today = timezone.localdate()

            if today != last_backup_date:
                backup = ensure_daily_backup()
                last_backup_date = today

                if backup is not None:
                    PUSH_LOGGER.info(
                        "Copia diaria verificada: %s.",
                        backup.name,
                    )
        except Exception:
            PUSH_LOGGER.exception(
                "Falló la verificación de la copia diaria."
            )

        try:
            result = dispatch_due_push_notifications()

            if result.sent or result.failed or result.deactivated:
                PUSH_LOGGER.info(
                    "Web Push: %s enviados, %s fallidos y %s "
                    "suscripciones desactivadas.",
                    result.sent,
                    result.failed,
                    result.deactivated,
                )
        except Exception:
            PUSH_LOGGER.exception(
                "Falló una ejecución del programador Web Push."
            )
        finally:
            close_old_connections()

        PUSH_SCHEDULER_STOP.wait(interval)


def start_push_scheduler() -> bool:
    """Inicia el programador cuando el entorno del host lo solicita."""

    if not settings.AGENDE_PUSH_SCHEDULER_ENABLED:
        return True

    if not push_is_configured():
        PUSH_LOGGER.error(
            "El programador Web Push está activo pero faltan las variables "
            "VAPID."
        )
        return False

    scheduler_thread = threading.Thread(
        target=run_push_scheduler,
        name="bfgenda-web-push",
        daemon=True,
    )
    scheduler_thread.start()
    atexit.register(PUSH_SCHEDULER_STOP.set)
    return True


def main() -> int:
    """Inicia Waitress y mantiene un PID para detenerlo con seguridad."""

    host = os.getenv("AGENDE_HOST", "0.0.0.0").strip() or "0.0.0.0"
    port = service_port()
    threads = env_int("AGENDE_THREADS", 4)

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    atexit.register(remove_pid_file)

    if not start_push_scheduler():
        remove_pid_file()
        return 1

    LOGGER.info(
        "Iniciando BFGenda con Waitress en http://%s:%s/ (%s hilos).",
        host,
        port,
        threads,
    )

    try:
        serve(
            application,
            host=host,
            port=port,
            threads=threads,
            ident="BFGenda",
            channel_timeout=120,
            cleanup_interval=30,
        )
    except KeyboardInterrupt:
        LOGGER.info("BFGenda fue detenido desde la consola.")
    except Exception:
        LOGGER.exception("Waitress no pudo iniciar o se detuvo por un error.")
        return 1
    finally:
        remove_pid_file()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
