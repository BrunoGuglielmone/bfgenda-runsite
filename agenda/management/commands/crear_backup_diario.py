"""Garantiza una copia automática diaria de la base SQLite."""

from django.core.management.base import BaseCommand, CommandError

from agenda.services.backups import BackupError, ensure_daily_backup


class Command(BaseCommand):
    help = "Crea, si aún no existe, la copia automática del día."

    def handle(self, *args, **options):
        try:
            backup = ensure_daily_backup()
        except BackupError as error:
            raise CommandError(str(error)) from error

        if backup is None:
            self.stdout.write("Las copias automáticas están desactivadas.")
            return

        self.stdout.write(
            self.style.SUCCESS(f"Copia diaria verificada: {backup.name}")
        )
