"""Envía los recordatorios Web Push que hayan vencido."""

from django.core.management.base import BaseCommand, CommandError

from agenda.services.webpush import (
    PushConfigurationError,
    dispatch_due_push_notifications,
)


class Command(BaseCommand):
    help = "Envía recordatorios vencidos a las suscripciones Web Push activas."

    def handle(self, *args, **options):
        try:
            result = dispatch_due_push_notifications()
        except PushConfigurationError as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            self.style.SUCCESS(
                "Web Push: "
                f"{result.sent} enviados, "
                f"{result.failed} fallidos, "
                f"{result.skipped} omitidos, "
                f"{result.deactivated} suscripciones desactivadas."
            )
        )
