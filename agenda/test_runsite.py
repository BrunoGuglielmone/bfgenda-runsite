"""Pruebas del arranque gratuito de Runsite respaldado por Litestream."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from scripts import iniciar_runsite_con_litestream


class RunsiteLitestreamStartupTests(TestCase):
    def test_crea_todas_las_rutas_configuradas(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = {
                "AGENDE_DATABASE_PATH": str(root / "database" / "db.sqlite3"),
                "AGENDE_BACKUP_DIR": str(root / "backups"),
                "AGENDE_LOG_DIR": str(root / "logs"),
            }

            with patch.dict(os.environ, environment, clear=False):
                iniciar_runsite_con_litestream.prepare_ephemeral_storage()
                self.assertEqual(
                    os.environ["AGENDE_DATABASE_PATH"],
                    environment["AGENDE_DATABASE_PATH"],
                )

            self.assertTrue((root / "database").is_dir())
            self.assertTrue((root / "backups").is_dir())
            self.assertTrue((root / "logs").is_dir())

    def test_litestream_restaura_y_supervisa_django(self):
        with (
            patch.dict(
                os.environ,
                {
                    "LITESTREAM_BUCKET": "bucket-prueba",
                    "LITESTREAM_ACCESS_KEY_ID": "id-prueba",
                    "LITESTREAM_SECRET_ACCESS_KEY": "secreto-prueba",
                },
            ),
            patch.object(
                iniciar_runsite_con_litestream,
                "prepare_ephemeral_storage",
            ),
            patch.object(os, "chdir"),
            patch.object(os, "execvp") as execvp,
        ):
            iniciar_runsite_con_litestream.main()

        execvp.assert_called_once()
        executable, arguments = execvp.call_args.args
        self.assertEqual(executable, "litestream")
        self.assertEqual(arguments[0:2], ["litestream", "replicate"])
        self.assertIn("-restore-if-db-not-exists", arguments)
        self.assertEqual(
            arguments[-2:], ["-exec", "python scripts/iniciar_runsite.py"]
        )

    def test_no_arranca_sin_persistencia_configurada(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(os, "execvp") as execvp,
            self.assertRaisesRegex(SystemExit, "LITESTREAM_BUCKET"),
        ):
            iniciar_runsite_con_litestream.main()
        execvp.assert_not_called()

    def test_rutas_vacias_utilizan_el_mismo_directorio_predeterminado(self):
        with patch.dict(
            os.environ,
            {
                "AGENDE_DATABASE_PATH": "",
                "AGENDE_BACKUP_DIR": "",
                "AGENDE_LOG_DIR": "",
            },
        ):
            paths = iniciar_runsite_con_litestream.configured_paths()
        root = iniciar_runsite_con_litestream.DEFAULT_DATA_DIR
        self.assertEqual(
            paths, (root / "db.sqlite3", root / "backups", root / "logs")
        )
