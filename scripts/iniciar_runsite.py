"""Prepara el almacenamiento persistente y arranca BFGenda en Runsite."""

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


def prepare_persistent_storage() -> None:
    """Crea las rutas configuradas antes de abrir SQLite o los registros."""

    Path(settings.DATABASES["default"]["NAME"]).parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    settings.AGENDE_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    settings.LOG_DIR.mkdir(parents=True, exist_ok=True)


def main() -> int:
    prepare_persistent_storage()
    call_command("migrate", interactive=False, verbosity=1)

    from scripts.servidor_agende import main as serve_main

    return serve_main()


if __name__ == "__main__":
    raise SystemExit(main())
