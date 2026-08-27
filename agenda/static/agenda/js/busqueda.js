"use strict";

/**
 * Búsqueda global de BFGenda.
 *
 * Actualiza los resultados mientras se escribe y permite abrir
 * el buscador desde cualquier pantalla con Ctrl/Cmd + K.
 */
document.addEventListener("DOMContentLoaded", () => {
    const SEARCH_DELAY = 260;
    let searchTimer = null;
    let activeController = null;

    function searchShellFrom(element) {
        return element?.closest("[data-search-shell]") || null;
    }

    function searchParts(shell) {
        if (!(shell instanceof HTMLElement)) {
            return null;
        }

        const input = shell.querySelector("[data-global-search-input]");
        const typeInput = shell.querySelector("[data-search-type-input]");
        const results = shell.querySelector("[data-search-results]");
        const form = shell.querySelector("[data-live-search-form]");
        const endpoint = shell.dataset.searchEndpoint || form?.action;

        if (
            !(input instanceof HTMLInputElement)
            || !(typeInput instanceof HTMLInputElement)
            || !(results instanceof HTMLElement)
            || !(form instanceof HTMLFormElement)
            || !endpoint
        ) {
            return null;
        }

        return {
            shell,
            input,
            typeInput,
            results,
            form,
            endpoint,
        };
    }

    function setActiveType(shell, selectedType) {
        shell.querySelectorAll("[data-search-type]").forEach((button) => {
            if (!(button instanceof HTMLButtonElement)) {
                return;
            }

            const active = button.dataset.searchType === selectedType;
            button.classList.toggle("active", active);
            button.setAttribute("aria-pressed", active ? "true" : "false");
        });
    }

    async function updateResults(parts) {
        activeController?.abort();
        activeController = new AbortController();
        parts.results.classList.add("searching");
        parts.results.setAttribute("aria-busy", "true");

        try {
            const url = new URL(parts.endpoint, window.location.href);
            url.searchParams.set("q", parts.input.value.trim());
            url.searchParams.set("tipo", parts.typeInput.value || "todo");
            url.searchParams.set("partial", "resultados");
            url.searchParams.set(
                "mode",
                parts.shell.dataset.searchMode || "modal"
            );

            const response = await fetch(url, {
                method: "GET",
                headers: {"X-Requested-With": "XMLHttpRequest"},
                credentials: "same-origin",
                signal: activeController.signal,
            });
            const data = await response.json();

            if (!response.ok || !data.html) {
                throw new Error("La búsqueda no devolvió resultados válidos.");
            }

            const wrapper = document.createElement("div");
            wrapper.innerHTML = data.html.trim();
            const newResults = wrapper.firstElementChild;

            if (!(newResults instanceof HTMLElement)) {
                throw new Error("No se pudo interpretar el resultado de la búsqueda.");
            }

            parts.results.replaceWith(newResults);
        } catch (error) {
            if (error instanceof DOMException && error.name === "AbortError") {
                return;
            }

            console.error("No se pudo actualizar la búsqueda:", error);
            parts.results.classList.remove("searching");
            parts.results.setAttribute("aria-busy", "false");
        }
    }

    function scheduleSearch(parts, immediate = false) {
        window.clearTimeout(searchTimer);

        if (immediate) {
            updateResults(parts);
            return;
        }

        searchTimer = window.setTimeout(() => {
            updateResults(parts);
        }, SEARCH_DELAY);
    }

    document.addEventListener("input", (event) => {
        const input = event.target;

        if (!(input instanceof HTMLInputElement)) {
            return;
        }

        if (!input.matches("[data-global-search-input]")) {
            return;
        }

        const parts = searchParts(searchShellFrom(input));

        if (parts) {
            scheduleSearch(parts);
        }
    });

    document.addEventListener("click", (event) => {
        if (!(event.target instanceof Element)) {
            return;
        }

        const typeButton = event.target.closest("[data-search-type]");

        if (!(typeButton instanceof HTMLButtonElement)) {
            return;
        }

        const parts = searchParts(searchShellFrom(typeButton));
        const selectedType = typeButton.dataset.searchType;

        if (!parts || !selectedType) {
            return;
        }

        parts.typeInput.value = selectedType;
        setActiveType(parts.shell, selectedType);
        scheduleSearch(parts, true);
    });

    document.addEventListener("submit", (event) => {
        const form = event.target;

        if (
            !(form instanceof HTMLFormElement)
            || !form.matches("[data-live-search-form]")
        ) {
            return;
        }

        const parts = searchParts(searchShellFrom(form));

        if (!parts) {
            return;
        }

        event.preventDefault();
        scheduleSearch(parts, true);
    });

    document.addEventListener("keydown", (event) => {
        const isShortcut = (event.ctrlKey || event.metaKey)
            && event.key.toLowerCase() === "k";

        if (!isShortcut) {
            return;
        }

        event.preventDefault();
        const trigger = document.querySelector("[data-global-search-trigger]");
        const url = trigger?.getAttribute("href");

        if (url && window.AgendeApp?.openModal) {
            window.AgendeApp.openModal(url, trigger);
        }
    });
});
