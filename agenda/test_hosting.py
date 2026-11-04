"""Pruebas del arranque portable y PostgreSQL administrado."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured

from config.database import database_config
from scripts import iniciar_host, iniciar_runsite_con_litestream


class DatabaseEnvironmentTests(TestCase):
    def test_conserva_sqlite_sin_url_administrada(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {
                "DATABASE_URL": "",
                "POSTGRES_URI": "",
                "AGENDE_DATABASE_PATH": "",
            },
            clear=False,
        ):
            config = database_config(Path(directory))

        self.assertEqual(config["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(config["NAME"], Path(directory) / "db.sqlite3")

    def test_interpreta_url_postgresql_y_opciones_tls(self):
        url = (
            "postgresql://usuario:secreto%20seguro@postgres.internal:5432/"
            "bfgenda?sslmode=require&application_name=ignorado"
        )
        with patch.dict(os.environ, {"DATABASE_URL": url}, clear=False):
            config = database_config(Path("/app"))

        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(config["NAME"], "bfgenda")
        self.assertEqual(config["USER"], "usuario")
        self.assertEqual(config["PASSWORD"], "secreto seguro")
        self.assertEqual(config["HOST"], "postgres.internal")
        self.assertEqual(config["OPTIONS"], {"sslmode": "require"})

    def test_rechaza_un_motor_no_admitido(self):
        with (
            patch.dict(
                os.environ,
                {"DATABASE_URL": "mysql://host/bfgenda"},
                clear=False,
            ),
            self.assertRaises(ImproperlyConfigured),
        ):
            database_config(Path("/app"))


class ManagedHostStartupTests(TestCase):
    def test_postgresql_arranca_django_sin_litestream(self):
        with (
            patch.dict(
                os.environ,
                {"DATABASE_URL": "postgresql://user:pass@db/bfgenda"},
                clear=False,
            ),
            patch.object(os, "chdir"),
            patch.object(os, "execv") as execv,
            patch.object(iniciar_runsite_con_litestream, "main") as litestream,
        ):
            iniciar_host.main()

        execv.assert_called_once_with(
            sys.executable,
            [
                sys.executable,
                str(iniciar_host.BASE_DIR / "scripts" / "iniciar_runsite.py"),
            ],
        )
        litestream.assert_not_called()

    def test_sqlite_conserva_supervision_litestream(self):
        with (
            patch.dict(
                os.environ,
                {"DATABASE_URL": "", "POSTGRES_URI": ""},
                clear=False,
            ),
            patch.object(os, "chdir"),
            patch.object(iniciar_runsite_con_litestream, "main") as litestream,
        ):
            iniciar_host.main()

        litestream.assert_called_once_with()
