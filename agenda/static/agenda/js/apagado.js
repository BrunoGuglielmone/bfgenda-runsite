"use strict";

/**
 * Informa cuándo el servidor local terminó de apagarse.
 *
 * Mientras Waitress continúa activo, el punto de estado responde. Cuando el
 * proceso finaliza, las comprobaciones de red fallan y la página ya cargada
 * puede cambiar su mensaje sin depender nuevamente de Django.
 */
document.addEventListener("DOMContentLoaded", () => {

    if ("scrollRestoration" in window.history) {
        window.history.scrollRestoration = "manual";
    }

    window.scrollTo(0, 0);

    window.addEventListener("pageshow", () => {
        window.scrollTo(0, 0);
    });
    const card = document.querySelector("[data-shutdown-status]");

    if (!(card instanceof HTMLElement)) {
        return;
    }

    const statusUrl = card.dataset.statusUrl;
    const title = card.querySelector("[data-shutdown-title]");
    const description = card.querySelector(
        "[data-shutdown-description]"
    );
    const note = card.querySelector("[data-shutdown-note]");

    if (
        !statusUrl
        || !(title instanceof HTMLElement)
        || !(description instanceof HTMLElement)
        || !(note instanceof HTMLElement)
    ) {
        return;
    }

    const POLL_INTERVAL_MS = 700;
    const REQUEST_TIMEOUT_MS = 1500;
    const REQUIRED_FAILURES = 2;
    const SLOW_WARNING_MS = 15000;

    let consecutiveFailures = 0;
    let finished = false;

    function markAsStopped() {
        if (finished) {
            return;
        }

        finished = true;
        card.classList.remove("is-delayed");
        card.classList.add("is-stopped");

        document.title = "BFGenda se detuvo";
        title.textContent = "BFGenda se detuvo correctamente";
        description.textContent = (
            "El servidor ya no está activo. Puedes cerrar esta pestaña "
            + "con tranquilidad."
        );
        note.innerHTML = (
            "Para volver a utilizar la aplicación, abre nuevamente el acceso "
            + "directo <strong>BFGenda</strong> del Escritorio."
        );
    }

    function markAsDelayed() {
        if (finished) {
            return;
        }

        card.classList.add("is-delayed");
        title.textContent = "El apagado está tardando más de lo normal";
        description.textContent = (
            "BFGenda todavía responde. Espera unos segundos más; esta pantalla "
            + "seguirá comprobando el estado automáticamente."
        );
        note.innerHTML = (
            "Si el mensaje no cambia, utiliza el acceso directo "
            + "<strong>Detener BFGenda</strong> del Escritorio."
        );
    }

    async function checkServerStatus() {
        if (finished) {
            return;
        }

        const controller = new AbortController();
        const timeoutId = window.setTimeout(() => {
            controller.abort();
        }, REQUEST_TIMEOUT_MS);

        try {
            const requestUrl = new URL(statusUrl, window.location.origin);
            requestUrl.searchParams.set("_", Date.now().toString());

            const response = await fetch(requestUrl, {
                method: "GET",
                cache: "no-store",
                credentials: "same-origin",
                signal: controller.signal,
                headers: {
                    "Accept": "application/json",
                },
            });

            if (!response.ok) {
                throw new Error(`Estado HTTP ${response.status}`);
            }

            const data = await response.json();

            if (data.activo !== true) {
                throw new Error("El servidor no confirmó su estado.");
            }

            consecutiveFailures = 0;
        } catch (error) {
            consecutiveFailures += 1;

            if (consecutiveFailures >= REQUIRED_FAILURES) {
                markAsStopped();
                return;
            }
        } finally {
            window.clearTimeout(timeoutId);
        }

        window.setTimeout(checkServerStatus, POLL_INTERVAL_MS);
    }

    window.setTimeout(checkServerStatus, 600);
    window.setTimeout(markAsDelayed, SLOW_WARNING_MS);
});
