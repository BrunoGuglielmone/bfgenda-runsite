"""Configuración de base de datos portable para BFGenda."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from django.core.exceptions import ImproperlyConfigured


POSTGRES_SCHEMES = {"postgres", "postgresql"}
POSTGRES_OPTIONS = {
    "channel_binding",
    "sslcert",
    "sslkey",
    "sslmode",
    "sslrootcert",
    "target_session_attrs",
}


def _postgres_config(database_url: str) -> dict:
    parsed = urlparse(database_url)

    if parsed.scheme.lower() not in POSTGRES_SCHEMES:
        raise ImproperlyConfigured(
            "DATABASE_URL debe comenzar con postgres:// o postgresql://."
        )

    database_name = unquote(parsed.path.lstrip("/"))
    if not parsed.hostname or not database_name:
        raise ImproperlyConfigured(
            "DATABASE_URL debe incluir servidor y nombre de base de datos."
        )

    query = parse_qs(parsed.query, keep_blank_values=False)
    options = {
        key: values[-1]
        for key, values in query.items()
        if key in POSTGRES_OPTIONS and values
    }
    config = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": database_name,
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname,
        "PORT": str(parsed.port or 5432),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
    if options:
        config["OPTIONS"] = options
    return config


def database_config(base_dir: Path) -> dict:
    """Usa PostgreSQL en el host y conserva SQLite para el modo local."""

    database_url = (
        os.getenv("DATABASE_URL", "").strip()
        or os.getenv("POSTGRES_URI", "").strip()
    )
    if database_url:
        return _postgres_config(database_url)

    return {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(
            os.getenv("AGENDE_DATABASE_PATH")
            or base_dir / "db.sqlite3"
        ),
    }
