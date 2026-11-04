"""Aplica las migraciones y arranca BFGenda en un host administrado."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import django


BASE_DIR = Path(__file__).resolve().parent.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402
from django.core.management import call_command  # noqa: E402


def prepare_storage() -> None:
    """Crea las rutas locales necesarias antes de iniciar el servidor."""

    if settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
        Path(settings.DATABASES["default"]["NAME"]).parent.mkdir(
            parents=True,
            exist_ok=True,
        )
    settings.AGENDE_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    settings.LOG_DIR.mkdir(parents=True, exist_ok=True)


def main() -> int:
    prepare_storage()
    call_command("migrate", interactive=False, verbosity=1)

    from scripts.servidor_agende import main as serve_main

    return serve_main()


if __name__ == "__main__":
    raise SystemExit(main())
