"""Selecciona el arranque persistente apropiado para el entorno."""

from __future__ import annotations

import os
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def main() -> None:
    """Usa PostgreSQL directamente o Litestream para el legado SQLite."""

    os.chdir(BASE_DIR)
    if os.getenv("DATABASE_URL", "").strip() or os.getenv(
        "POSTGRES_URI", ""
    ).strip():
        os.execv(
            sys.executable,
            [sys.executable, str(BASE_DIR / "scripts" / "iniciar_runsite.py")],
        )
        return

    from scripts.iniciar_runsite_con_litestream import main as litestream_main

    litestream_main()


if __name__ == "__main__":
    main()
