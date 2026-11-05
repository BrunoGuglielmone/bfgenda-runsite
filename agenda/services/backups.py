"""Copias de seguridad y restauración de la base SQLite de BFGenda."""

from __future__ import annotations

import os
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db import connections
from django.utils import timezone

from agenda.services.maintenance import maintenance_mode


BACKUP_AUTOMATIC = "automatic"
BACKUP_MANUAL = "manual"
BACKUP_PRE_RESTORE = "pre-restore"
BACKUP_KINDS = {
    BACKUP_AUTOMATIC: "Automática",
    BACKUP_MANUAL: "Manual",
    BACKUP_PRE_RESTORE: "Antes de restaurar",
}

AUTO_BACKUP_SESSION_KEY = "agende_auto_backup_checked_on"
DEFAULT_AUTO_BACKUP_LIMIT = 30
CURRENT_BACKUP_PREFIX = "bfgenda"
LEGACY_BACKUP_PREFIXES = ("agende",)
BACKUP_PREFIXES = (
    CURRENT_BACKUP_PREFIX,
    *LEGACY_BACKUP_PREFIXES,
)
REQUIRED_TABLES = {
    "auth_user",
    "agenda_categoria",
    "agenda_evento",
    "agenda_tarea",
    "django_migrations",
}

_BACKUP_PREFIX_PATTERN = "|".join(
    re.escape(prefix) for prefix in BACKUP_PREFIXES
)
_NAME_PATTERN = re.compile(
    rf"^(?:{_BACKUP_PREFIX_PATTERN})-"
    r"(automatic|manual|pre-restore)-"
    r"(?P<date>\d{8})-(?P<time>\d{6})-(?P<microseconds>\d{6})\.sqlite3$"
)
_BACKUP_LOCK = threading.RLock()


class BackupError(RuntimeError):
    """Error controlado relacionado con una copia de seguridad."""


@dataclass(frozen=True)
class BackupInfo:
    """Información segura y lista para mostrar de una copia local."""

    name: str
    path: Path
    kind: str
    created_at: datetime
    size_bytes: int

    @property
    def kind_label(self) -> str:
        return BACKUP_KINDS.get(self.kind, "Copia")

    @property
    def size_label(self) -> str:
        size = float(self.size_bytes)

        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                decimals = 0 if unit == "B" else 1
                return f"{size:.{decimals}f} {unit}"
            size /= 1024

        return f"{self.size_bytes} B"


@dataclass(frozen=True)
class RestoreResult:
    """Resultado de una restauración y copia de seguridad preventiva."""

    restored_backup: BackupInfo
    safety_backup: BackupInfo


def sqlite_backups_enabled() -> bool:
    """Indica si las copias integradas pueden operar en este entorno."""

    return (
        settings.DATABASES["default"].get("ENGINE")
        == "django.db.backends.sqlite3"
    )


def get_database_path(database_path=None) -> Path:
    """Obtiene la ruta SQLite configurada y rechaza otros motores."""

    if database_path is not None:
        return Path(database_path).resolve()

    database = settings.DATABASES["default"]

    if database.get("ENGINE") != "django.db.backends.sqlite3":
        raise BackupError("Las copias integradas solo admiten SQLite.")

    name = str(database.get("NAME", ""))

    if not name or name == ":memory:" or name.startswith("file:"):
        raise BackupError("La base de datos actual no es un archivo SQLite local.")

    return Path(name).resolve()


def get_backup_directory(backup_dir=None) -> Path:
    """Devuelve la carpeta privada de copias y la crea cuando hace falta."""

    directory = Path(
        backup_dir
        or getattr(settings, "AGENDE_BACKUP_DIR", settings.BASE_DIR / "backups")
    ).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def automatic_backup_limit() -> int:
    """Cantidad máxima de copias automáticas conservadas."""

    value = int(
        getattr(settings, "AGENDE_AUTO_BACKUP_LIMIT", DEFAULT_AUTO_BACKUP_LIMIT)
    )
    return max(value, 1)


def _local_now(now=None) -> datetime:
    value = now or timezone.now()

    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())

    return timezone.localtime(value)


def _backup_filename(kind: str, now=None) -> str:
    if kind not in BACKUP_KINDS:
        raise BackupError("El tipo de copia solicitado no es válido.")

    current = _local_now(now)
    return (
        f"{CURRENT_BACKUP_PREFIX}-{kind}-"
        f"{current:%Y%m%d-%H%M%S-%f}.sqlite3"
    )


def _parse_backup(path: Path) -> BackupInfo | None:
    match = _NAME_PATTERN.fullmatch(path.name)

    if match is None or not path.is_file():
        return None

    created_naive = datetime.strptime(
        (
            f"{match.group('date')}"
            f"{match.group('time')}"
            f"{match.group('microseconds')}"
        ),
        "%Y%m%d%H%M%S%f",
    )
    created_at = timezone.make_aware(
        created_naive,
        timezone.get_current_timezone(),
    )
    return BackupInfo(
        name=path.name,
        path=path,
        kind=match.group(1),
        created_at=created_at,
        size_bytes=path.stat().st_size,
    )


def list_backups(*, backup_dir=None) -> list[BackupInfo]:
    """Lista únicamente copias cuyo nombre fue generado por BFGenda."""

    directory = get_backup_directory(backup_dir)
    backups = []

    for path in directory.glob("*.sqlite3"):
        info = _parse_backup(path)
        if info is not None:
            backups.append(info)

    return sorted(backups, key=lambda item: item.created_at, reverse=True)


def get_backup(backup_name: str, *, backup_dir=None) -> BackupInfo:
    """Resuelve una copia sin permitir escapar de la carpeta configurada."""

    if not backup_name or Path(backup_name).name != backup_name:
        raise BackupError("El nombre de la copia no es válido.")

    directory = get_backup_directory(backup_dir)
    path = (directory / backup_name).resolve()

    if path.parent != directory:
        raise BackupError("La copia solicitada no pertenece a BFGenda.")

    info = _parse_backup(path)

    if info is None:
        raise BackupError("La copia solicitada no existe.")

    return info


def _database_tables(connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {row[0] for row in rows}


def _table_columns(connection, table_name: str) -> set[str]:
    safe_table_name = table_name.replace('"', '""')
    rows = connection.execute(
        f'PRAGMA table_info("{safe_table_name}")'
    ).fetchall()
    return {row[1] for row in rows}


def _applied_migrations(connection) -> set[tuple[str, str]]:
    rows = connection.execute(
        "SELECT app, name FROM django_migrations"
    ).fetchall()
    return {(row[0], row[1]) for row in rows}


def validate_sqlite_database(
    path: Path,
    *,
    reference_path: Path | None = None,
) -> None:
    """
    Comprueba integridad, tablas, columnas y migraciones.

    Si se proporciona una base de referencia, la copia debe contener
    como minimo su esquema y sus migraciones aplicadas.
    """

    path = Path(path)

    if not path.is_file() or path.stat().st_size < 100:
        raise BackupError(
            "El archivo no contiene una base SQLite valida."
        )

    reference = (
        Path(reference_path)
        if reference_path is not None
        else None
    )

    if reference is not None and not reference.is_file():
        raise BackupError(
            "No fue posible localizar la base de referencia "
            "de BFGenda."
        )

    try:
        with path.open("rb") as source:
            if source.read(16) != b"SQLite format 3\x00":
                raise BackupError(
                    "El archivo no tiene el encabezado de SQLite."
                )

        connection = sqlite3.connect(str(path), timeout=30)

        try:
            result = connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()

            if not result or result[0] != "ok":
                raise BackupError(
                    "SQLite informo que la copia esta danada."
                )

            tables = _database_tables(connection)
            missing_tables = REQUIRED_TABLES - tables

            if missing_tables:
                names = ", ".join(sorted(missing_tables))
                raise BackupError(
                    "La copia no contiene la estructura minima "
                    f"de BFGenda. Faltan tablas: {names}."
                )

            if reference is None:
                return

            reference_connection = sqlite3.connect(
                str(reference),
                timeout=30,
            )

            try:
                reference_tables = _database_tables(
                    reference_connection
                )

                tables_to_compare = (
                    REQUIRED_TABLES & reference_tables
                )

                for table_name in sorted(tables_to_compare):
                    expected_columns = _table_columns(
                        reference_connection,
                        table_name,
                    )
                    backup_columns = _table_columns(
                        connection,
                        table_name,
                    )
                    missing_columns = (
                        expected_columns - backup_columns
                    )

                    if missing_columns:
                        names = ", ".join(
                            sorted(missing_columns)
                        )
                        raise BackupError(
                            "La copia pertenece a una version "
                            "incompatible de BFGenda. "
                            f"En {table_name} faltan columnas: "
                            f"{names}."
                        )

                expected_migrations = _applied_migrations(
                    reference_connection
                )
                backup_migrations = _applied_migrations(
                    connection
                )
                missing_migrations = (
                    expected_migrations - backup_migrations
                )

                if missing_migrations:
                    sample = ", ".join(
                        f"{app}.{name}"
                        for app, name in sorted(
                            missing_migrations
                        )[:5]
                    )
                    raise BackupError(
                        "La copia pertenece a una version anterior "
                        "o incompatible de BFGenda. "
                        "Faltan migraciones aplicadas: "
                        f"{sample}."
                    )
            finally:
                reference_connection.close()
        finally:
            connection.close()

    except sqlite3.DatabaseError as error:
        raise BackupError(
            "No fue posible validar la copia SQLite."
        ) from error


def _copy_database_with_sqlite(source_path: Path, destination_path: Path) -> None:
    """Usa la API de respaldo de SQLite, incluso con la app abierta."""

    source_connection = sqlite3.connect(str(source_path), timeout=30)
    destination_connection = sqlite3.connect(str(destination_path), timeout=30)

    try:
        source_connection.backup(destination_connection)
        destination_connection.commit()
    except sqlite3.DatabaseError as error:
        raise BackupError("SQLite no pudo crear la copia de seguridad.") from error
    finally:
        destination_connection.close()
        source_connection.close()


def prune_automatic_backups(*, backup_dir=None, limit=None) -> int:
    """Conserva las copias automáticas más recientes y no toca las manuales."""

    keep = max(int(limit or automatic_backup_limit()), 1)
    automatic = [
        backup
        for backup in list_backups(backup_dir=backup_dir)
        if backup.kind == BACKUP_AUTOMATIC
    ]
    removed = 0

    for backup in automatic[keep:]:
        backup.path.unlink(missing_ok=True)
        removed += 1

    return removed


def create_backup(
    kind: str = BACKUP_MANUAL,
    *,
    database_path=None,
    backup_dir=None,
    now=None,
) -> BackupInfo:
    """Crea una copia íntegra y atómica de la base de datos actual."""

    source = get_database_path(database_path)

    if not source.is_file():
        raise BackupError("No se encontró la base de datos de BFGenda.")

    directory = get_backup_directory(backup_dir)
    destination = directory / _backup_filename(kind, now)
    temporary = destination.with_suffix(".tmp")

    with _BACKUP_LOCK:
        try:
            temporary.unlink(missing_ok=True)
            _copy_database_with_sqlite(source, temporary)
            validate_sqlite_database(
                temporary,
                reference_path=source,
            )
            os.replace(temporary, destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

        if kind == BACKUP_AUTOMATIC:
            prune_automatic_backups(backup_dir=directory)

    info = _parse_backup(destination)

    if info is None:
        raise BackupError("La copia se creó, pero no pudo registrarse.")

    return info


def ensure_daily_backup(*, database_path=None, backup_dir=None, now=None):
    """Crea como máximo una copia automática por fecha local."""

    if not getattr(settings, "AGENDE_AUTOMATIC_BACKUPS", True):
        return None

    if database_path is None:
        configured_name = str(settings.DATABASES["default"].get("NAME", ""))
        if (
            not configured_name
            or configured_name == ":memory:"
            or configured_name.startswith("file:")
        ):
            return None

    current = _local_now(now)
    expected_date = current.date()

    with _BACKUP_LOCK:
        existing = next(
            (
                backup
                for backup in list_backups(backup_dir=backup_dir)
                if backup.kind == BACKUP_AUTOMATIC
                and backup.created_at.date() == expected_date
            ),
            None,
        )

        if existing is not None:
            return existing

        return create_backup(
            BACKUP_AUTOMATIC,
            database_path=database_path,
            backup_dir=backup_dir,
            now=current,
        )


def restore_backup(
    backup_name: str,
    *,
    database_path=None,
    backup_dir=None,
    now=None,
) -> RestoreResult:
    """Restaura una copia validada y conserva el estado anterior."""

    selected = get_backup(backup_name, backup_dir=backup_dir)
    database = get_database_path(database_path)
    validate_sqlite_database(
        selected.path,
        reference_path=database,
    )
    safety = create_backup(
        BACKUP_PRE_RESTORE,
        database_path=database,
        backup_dir=backup_dir,
        now=now,
    )

    with maintenance_mode():
        with _BACKUP_LOCK:
            connections.close_all()

            try:
                _copy_database_with_sqlite(
                    selected.path,
                    database,
                )
                validate_sqlite_database(
                    database,
                    reference_path=selected.path,
                )
            except Exception as error:
                try:
                    _copy_database_with_sqlite(
                        safety.path,
                        database,
                    )
                    validate_sqlite_database(
                        database,
                        reference_path=safety.path,
                    )
                except Exception as recovery_error:
                    raise BackupError(
                        "La restauracion fallo y BFGenda tampoco "
                        "pudo recuperar automaticamente el estado "
                        "anterior."
                    ) from recovery_error

                if isinstance(error, BackupError):
                    raise

                raise BackupError(
                    "No fue posible restaurar la copia "
                    "seleccionada. Se recupero el estado anterior."
                ) from error
            finally:
                connections.close_all()

    return RestoreResult(restored_backup=selected, safety_backup=safety)
