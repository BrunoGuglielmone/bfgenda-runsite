from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from agenda.models import Evento
from agenda.services.event_queries import (
    event_counts,
    event_queryset_for_filter,
)


AJAX_HEADERS = {
    "HTTP_X_REQUESTED_WITH": "XMLHttpRequest",
}


def aware_delta(**kwargs):
    return timezone.now() + timedelta(**kwargs)


class EventLifecycleTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="ciclo-eventos",
            password="clave-segura",
        )
        self.other_user = user_model.objects.create_user(
            username="otro-ciclo",
            password="otra-clave",
        )
        self.client.force_login(self.user)

    def create_event(
        self,
        *,
        title,
        start_delta,
        end_delta,
        state=Evento.Estado.PROGRAMADO,
        user=None,
    ):
        return Evento.objects.create(
            usuario=user or self.user,
            titulo=title,
            inicio=aware_delta(**start_delta),
            fin=aware_delta(**end_delta),
            estado=state,
        )

    def test_past_filter_is_automatic(self):
        past = self.create_event(
            title="Evento pasado",
            start_delta={"hours": -2},
            end_delta={"hours": -1},
        )
        self.create_event(
            title="Evento futuro",
            start_delta={"hours": 1},
            end_delta={"hours": 2},
        )

        results = event_queryset_for_filter(
            self.user,
            "pasados",
        )

        self.assertEqual(list(results), [past])

    def test_cancelled_event_is_not_counted_as_past(self):
        self.create_event(
            title="Cancelado antiguo",
            start_delta={"hours": -2},
            end_delta={"hours": -1},
            state=Evento.Estado.CANCELADO,
        )

        counts = event_counts(self.user)

        self.assertEqual(counts["cantidad_eventos_pasados"], 0)
        self.assertEqual(counts["cantidad_eventos_cancelados"], 1)

    def test_events_page_removes_manual_status_filters(self):
        self.create_event(
            title="Próximo compromiso",
            start_delta={"hours": 1},
            end_delta={"hours": 2},
        )

        response = self.client.get(
            reverse("agenda:eventos_listado")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pasados")
        self.assertNotContains(response, ">Programados<")
        self.assertNotContains(response, ">Realizados<")
        self.assertContains(
            response,
            "Cancelar evento Próximo compromiso",
        )

    def test_cancel_and_restore_event(self):
        event = self.create_event(
            title="Consulta",
            start_delta={"hours": 1},
            end_delta={"hours": 2},
        )

        cancel_response = self.client.post(
            reverse(
                "agenda:evento_cancelar",
                args=[event.id],
            ),
            **AJAX_HEADERS,
        )

        self.assertEqual(cancel_response.status_code, 200)
        event.refresh_from_db()
        self.assertEqual(
            event.estado,
            Evento.Estado.CANCELADO,
        )

        restore_response = self.client.post(
            reverse(
                "agenda:evento_restaurar",
                args=[event.id],
            ),
            **AJAX_HEADERS,
        )

        self.assertEqual(restore_response.status_code, 200)
        event.refresh_from_db()
        self.assertEqual(
            event.estado,
            Evento.Estado.PROGRAMADO,
        )

    def test_cancel_and_restore_require_post(self):
        event = self.create_event(
            title="Acción protegida",
            start_delta={"hours": 1},
            end_delta={"hours": 2},
        )

        self.assertEqual(
            self.client.get(
                reverse(
                    "agenda:evento_cancelar",
                    args=[event.id],
                )
            ).status_code,
            405,
        )
        self.assertEqual(
            self.client.get(
                reverse(
                    "agenda:evento_restaurar",
                    args=[event.id],
                )
            ).status_code,
            405,
        )

    def test_other_users_event_cannot_be_cancelled(self):
        event = self.create_event(
            title="Evento ajeno",
            start_delta={"hours": 1},
            end_delta={"hours": 2},
            user=self.other_user,
        )

        response = self.client.post(
            reverse(
                "agenda:evento_cancelar",
                args=[event.id],
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_recent_past_event_endpoint_returns_modal_url(self):
        event = self.create_event(
            title="Clase recién terminada",
            start_delta={"hours": -2},
            end_delta={"minutes": -30},
        )

        response = self.client.get(
            reverse("agenda:evento_pasado_pendiente")
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["event"]["id"], event.id)
        self.assertEqual(
            payload["event"]["modal_url"],
            reverse(
                "agenda:evento_pasado_aviso",
                args=[event.id],
            ),
        )
        self.assertEqual(
            response["Cache-Control"],
            "no-store",
        )

    def test_old_past_event_is_not_returned_for_notice(self):
        self.create_event(
            title="Evento demasiado antiguo",
            start_delta={"hours": -27},
            end_delta={"hours": -26},
        )

        response = self.client.get(
            reverse("agenda:evento_pasado_pendiente")
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["event"])

    def test_cancelled_event_is_not_returned_for_notice(self):
        self.create_event(
            title="Evento cancelado recientemente",
            start_delta={"hours": -2},
            end_delta={"minutes": -30},
            state=Evento.Estado.CANCELADO,
        )

        response = self.client.get(
            reverse("agenda:evento_pasado_pendiente")
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["event"])

    def test_past_event_modal_contains_three_decisions(self):
        event = self.create_event(
            title="Reunión finalizada",
            start_delta={"hours": -2},
            end_delta={"minutes": -30},
        )

        response = self.client.get(
            reverse(
                "agenda:evento_pasado_aviso",
                args=[event.id],
            ),
            **AJAX_HEADERS,
        )

        self.assertEqual(response.status_code, 200)
        html = response.json()["html"]
        self.assertIn("Mantener en Pasados", html)
        self.assertIn("Cancelar evento", html)
        self.assertIn("Eliminar evento", html)
        self.assertIn(
            reverse(
                "agenda:evento_cancelar",
                args=[event.id],
            ),
            html,
        )
        self.assertIn(
            reverse(
                "agenda:evento_eliminar",
                args=[event.id],
            ),
            html,
        )
        self.assertIn(
            'data-modal-url="',
            html,
        )

    def test_past_event_notice_is_private(self):
        foreign_event = self.create_event(
            title="Evento pasado ajeno",
            start_delta={"hours": -2},
            end_delta={"minutes": -30},
            user=self.other_user,
        )

        response = self.client.get(
            reverse(
                "agenda:evento_pasado_aviso",
                args=[foreign_event.id],
            )
        )

        self.assertEqual(response.status_code, 404)
