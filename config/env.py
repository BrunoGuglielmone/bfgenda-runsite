"""Utilidades mínimas para la configuración local de BFGenda.

El proyecto usa un archivo ``.env`` privado, sin dependencias externas,
para conservar secretos y opciones de ejecución propias de cada equipo.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Iterable


def load_env_file(path: Path) -> None:
    """Carga pares ``CLAVE=VALOR`` sin sobrescribir el entorno existente."""

    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key:
            continue

        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {'"', "'"}
        ):
            value = value[1:-1]

        os.environ.setdefault(key, value)


def env_bool(name: str, default: bool = False) -> bool:
    """Interpreta una variable de entorno como valor booleano."""

    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
        "si",
        "sí",
    }


def env_int(name: str, default: int, *, minimum: int = 1) -> int:
    """Obtiene un entero y aplica un mínimo seguro."""

    value = os.getenv(name)

    if value is None:
        return default

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default

    return max(parsed, minimum)


def env_list(
    name: str,
    default: Iterable[str] = (),
) -> list[str]:
    """Convierte una variable separada por comas en una lista limpia."""

    value = os.getenv(name)

    if not value:
        return list(default)

    return [
        item.strip()
        for item in value.split(",")
        if item.strip()
    ]


def local_ipv4_addresses() -> list[str]:
    """Devuelve direcciones IPv4 locales detectadas para ALLOWED_HOSTS."""

    addresses: set[str] = set()

    try:
        host_name = socket.gethostname()
        _, _, detected = socket.gethostbyname_ex(host_name)

        for address in detected:
            if address and not address.startswith("127."):
                addresses.add(address)
    except OSError:
        pass

    return sorted(addresses)
