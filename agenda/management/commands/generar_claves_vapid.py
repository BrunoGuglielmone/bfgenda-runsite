"""Genera el par de claves VAPID sin guardar secretos en Git."""

from __future__ import annotations

import base64
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Genera una clave privada PEM y muestra su clave pública Web Push."

    def add_arguments(self, parser):
        parser.add_argument(
            "private_key_file",
            help="Ruta nueva donde guardar la clave privada PEM.",
        )
        parser.add_argument(
            "--public-key-file",
            help=(
                "Ruta nueva opcional donde guardar la clave pública "
                "Web Push."
            ),
        )

    def handle(self, *args, **options):
        path = Path(options["private_key_file"]).expanduser().resolve()

        if path.exists():
            raise CommandError(
                "La ruta ya existe; no se sobrescribió ninguna clave."
            )

        path.parent.mkdir(parents=True, exist_ok=True)
        private_key = ec.generate_private_key(ec.SECP256R1())
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        path.write_bytes(private_pem)

        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

        public_bytes = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        public_key = base64.urlsafe_b64encode(public_bytes).rstrip(b"=")
        public_key_text = public_key.decode("ascii")

        public_key_file = options.get("public_key_file")
        if public_key_file:
            public_path = Path(public_key_file).expanduser().resolve()
            if public_path.exists():
                path.unlink(missing_ok=True)
                raise CommandError(
                    "La ruta de la clave pública ya existe; no se "
                    "guardó el nuevo par."
                )
            public_path.parent.mkdir(parents=True, exist_ok=True)
            public_path.write_text(public_key_text, encoding="ascii")

        self.stdout.write(self.style.SUCCESS("Claves VAPID generadas."))
        self.stdout.write(f"AGENDE_VAPID_PRIVATE_KEY={path}")
        self.stdout.write(f"AGENDE_VAPID_PUBLIC_KEY={public_key_text}")
