"""Prepara el volumen efimero y delega el ciclo de vida a Litestream."""

from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = Path("/data/bfgenda")


def configured_paths() -> tuple[Path, Path, Path]:
    """Devuelve las rutas que la aplicacion utilizara dentro del contenedor."""

    database_path = Path(
        os.getenv("AGENDE_DATABASE_PATH") or DEFAULT_DATA_DIR / "db.sqlite3"
    )
    backup_dir = Path(
        os.getenv("AGENDE_BACKUP_DIR") or DEFAULT_DATA_DIR / "backups"
    )
    log_dir = Path(os.getenv("AGENDE_LOG_DIR") or DEFAULT_DATA_DIR / "logs")
    return database_path, backup_dir, log_dir


def prepare_ephemeral_storage() -> None:
    """Crea las carpetas que Runsite entrega vacias tras cada reinicio."""

    database_path, backup_dir, log_dir = configured_paths()
    # Django y el YAML de Litestream deben recibir exactamente las mismas rutas.
    os.environ["AGENDE_DATABASE_PATH"] = str(database_path)
    os.environ["AGENDE_BACKUP_DIR"] = str(backup_dir)
    os.environ["AGENDE_LOG_DIR"] = str(log_dir)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)


def main() -> None:
    missing = [
        name
        for name in (
            "LITESTREAM_BUCKET",
            "LITESTREAM_ACCESS_KEY_ID",
            "LITESTREAM_SECRET_ACCESS_KEY",
        )
        if not os.getenv(name, "").strip()
    ]
    if missing:
        raise SystemExit("Falta configurar la persistencia S3: " + ", ".join(missing))

    prepare_ephemeral_storage()
    os.chdir(BASE_DIR)
    os.execvp(
        "litestream",
        [
            "litestream",
            "replicate",
            "-config",
            str(BASE_DIR / "deployment" / "litestream.yml"),
            "-restore-if-db-not-exists",
            "-exec",
            "python scripts/iniciar_runsite.py",
        ],
    )


if __name__ == "__main__":
    main()
