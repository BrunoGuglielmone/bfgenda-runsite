"use strict";

/**
 * Interacción específica del calendario.
 *
 * Cambia entre día, semana y mes sin recargar. En la vista mensual,
 * seleccionar un día actualiza el panel y, cuando tiene contenido,
 * abre una vista rápida de solo lectura.
 */
document.addEventListener("DOMContentLoaded", () => {
    function revealSelectedWeekDay() {
        const scroller = document.querySelector(".week-calendar-scroll");
        const selectedDay = scroller?.querySelector(".week-day.selected");

        if (
            window.innerWidth > 760
            || !(scroller instanceof HTMLElement)
            || !(selectedDay instanceof HTMLElement)
        ) {
            return;
        }

        const scrollerRect = scroller.getBoundingClientRect();
        const selectedRect = selectedDay.getBoundingClientRect();
        const safeMargin = 10;
        const isVisible = (
            selectedRect.left >= scrollerRect.left + safeMargin
            && selectedRect.right <= scrollerRect.right - safeMargin
        );

        if (isVisible) {
            return;
        }

        const centeredPosition = (
            selectedDay.offsetLeft
            - ((scroller.clientWidth - selectedDay.offsetWidth) / 2)
        );

        scroller.scrollTo({
            left: Math.max(centeredPosition, 0),
            behavior: "auto",
        });
    }

    function initializeCalendarViewport() {
        window.requestAnimationFrame(revealSelectedWeekDay);
    }

    function updateHeaderEventButton(dateValue) {
        const button = document.querySelector("[data-calendar-header-event]");

        if (!(button instanceof HTMLAnchorElement)) {
            return;
        }

        const baseUrl = button.dataset.baseUrl;

        if (!baseUrl) {
            return;
        }

        const url = `${baseUrl}?fecha=${encodeURIComponent(dateValue)}`;
        button.href = url;
        button.dataset.modalUrl = url;
    }

    function selectMonthDay(cell) {
        const dateValue = cell.dataset.date;
        const templateId = cell.dataset.templateId;
        const template = templateId ? document.getElementById(templateId) : null;
        const panel = document.querySelector("#selected-day-panel");
        const calendar = cell.closest(".month-calendar");

        if (
            !dateValue
            || !(template instanceof HTMLTemplateElement)
            || !(panel instanceof HTMLElement)
            || !(calendar instanceof HTMLElement)
        ) {
            return;
        }

        calendar.querySelectorAll(".calendar-day[data-calendar-day]").forEach(
            (dayCell) => {
                dayCell.classList.remove("selected");
                dayCell.setAttribute("aria-selected", "false");
            }
        );

        cell.classList.add("selected");
        cell.setAttribute("aria-selected", "true");
        panel.replaceChildren(template.content.cloneNode(true));

        const url = new URL(window.location.href);
        url.searchParams.set("vista", "mes");
        url.searchParams.set("mes", dateValue.slice(0, 7));
        url.searchParams.set("dia", dateValue);
        window.history.replaceState({selectedDay: dateValue}, "", url);
        updateHeaderEventButton(dateValue);
    }

    async function openDaySummary(cell) {
        const modalUrl = cell.dataset.dayModalUrl;

        if (!modalUrl || !window.AgendeApp?.openModal) {
            return;
        }

        await window.AgendeApp.openModal(modalUrl, cell);
    }

    document.addEventListener("click", async (event) => {
        if (!(event.target instanceof Element)) {
            return;
        }

        if (
            event instanceof MouseEvent
            && (
                event.button !== 0
                || event.ctrlKey
                || event.metaKey
                || event.shiftKey
                || event.altKey
            )
        ) {
            return;
        }

        const navigationLink = event.target.closest("[data-calendar-navigation]");

        if (navigationLink instanceof HTMLAnchorElement) {
            event.preventDefault();

            if (window.AgendeApp?.navigate) {
                await window.AgendeApp.navigate(navigationLink.href);
            } else {
                window.location.assign(navigationLink.href);
            }
            return;
        }

        const calendar = event.target.closest(".month-calendar");

        if (!(calendar instanceof HTMLElement)) {
            return;
        }

        if (event.target.closest(".calendar-mini-item")) {
            return;
        }

        const cell = event.target.closest(".calendar-day[data-calendar-day]");

        if (!(cell instanceof HTMLElement)) {
            return;
        }

        const dayLink = cell.querySelector(".calendar-day-number");

        if (cell.classList.contains("outside-month")) {
            if (dayLink instanceof HTMLAnchorElement) {
                event.preventDefault();

                if (window.AgendeApp?.navigate) {
                    await window.AgendeApp.navigate(dayLink.href);
                } else {
                    window.location.assign(dayLink.href);
                }
            }
            return;
        }

        event.preventDefault();
        selectMonthDay(cell);
        await openDaySummary(cell);
    });

    document.addEventListener(
        "agende:content-updated",
        initializeCalendarViewport
    );
    initializeCalendarViewport();
});
