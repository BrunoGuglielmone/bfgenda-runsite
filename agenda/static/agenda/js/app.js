"use strict";

/**
 * Cliente global de BFGenda.
 *
 * Centraliza modales, formularios AJAX, navegación parcial,
 * refresco del contenido y mensajes breves sin recargar la página.
 */
document.addEventListener("DOMContentLoaded", () => {
    const dialog = document.querySelector("#app-modal");
    const modalContent = document.querySelector("#app-modal-content");
    const toast = document.querySelector("#app-toast");
    let modalTrigger = null;
    let toastTimer = null;
    let filterSwipeDirection = null;
    let filterSwipeInProgress = false;

    function currentRelativeUrl() {
        return `${window.location.pathname}${window.location.search}`;
    }

    function withReturnUrl(rawUrl) {
        const url = new URL(rawUrl, window.location.href);

        if (!url.searchParams.has("return_url")) {
            url.searchParams.set("return_url", currentRelativeUrl());
        }

        return url;
    }

    function showToast(message, type = "success") {
        if (!(toast instanceof HTMLElement) || !message) {
            return;
        }

        window.clearTimeout(toastTimer);
        toast.textContent = message;
        toast.dataset.type = type;
        toast.classList.add("visible");

        toastTimer = window.setTimeout(() => {
            toast.classList.remove("visible");
        }, 3200);
    }

    function captureNestedScroll() {
        const positions = new Map();

        document.querySelectorAll("[data-scroll-key]").forEach((element) => {
            if (!(element instanceof HTMLElement)) {
                return;
            }

            const key = element.dataset.scrollKey;

            if (key) {
                positions.set(key, {
                    left: element.scrollLeft,
                    top: element.scrollTop,
                });
            }
        });

        return positions;
    }

    function restoreNestedScroll(positions) {
        document.querySelectorAll("[data-scroll-key]").forEach((element) => {
            if (!(element instanceof HTMLElement)) {
                return;
            }

            const key = element.dataset.scrollKey;
            const position = key ? positions.get(key) : null;

            if (position) {
                element.scrollLeft = position.left;
                element.scrollTop = position.top;
            }
        });
    }

    function absoluteAssetUrl(rawUrl) {
        return new URL(rawUrl, window.location.href).href;
    }

    async function synchronizePageStyles(parsedDocument) {
        const currentStyles = new Map(
            Array.from(
                document.head.querySelectorAll(
                    'link[rel="stylesheet"][data-page-style]'
                )
            ).map((link) => [
                absoluteAssetUrl(link.getAttribute("href") || link.href),
                link,
            ])
        );
        const targetStyles = Array.from(
            parsedDocument.head.querySelectorAll(
                'link[rel="stylesheet"][data-page-style]'
            )
        );
        const targetUrls = new Set(
            targetStyles.map((link) => absoluteAssetUrl(
                link.getAttribute("href") || link.href
            ))
        );
        const pendingLoads = [];

        targetStyles.forEach((targetStyle) => {
            const targetUrl = absoluteAssetUrl(
                targetStyle.getAttribute("href") || targetStyle.href
            );

            if (currentStyles.has(targetUrl)) {
                return;
            }

            const newStyle = document.createElement("link");

            Array.from(targetStyle.attributes).forEach((attribute) => {
                newStyle.setAttribute(attribute.name, attribute.value);
            });

            pendingLoads.push(new Promise((resolve, reject) => {
                newStyle.addEventListener("load", resolve, {once: true});
                newStyle.addEventListener(
                    "error",
                    () => reject(new Error(
                        `No se pudo cargar el estilo ${targetUrl}.`
                    )),
                    {once: true}
                );
            }));

            document.head.appendChild(newStyle);
        });

        await Promise.all(pendingLoads);

        currentStyles.forEach((style, styleUrl) => {
            if (!targetUrls.has(styleUrl)) {
                style.remove();
            }
        });
    }

    function synchronizeApplicationShell(parsedDocument) {
        [".sidebar", ".mobile-navigation"].forEach((selector) => {
            const currentElement = document.querySelector(selector);
            const targetElement = parsedDocument.querySelector(selector);

            if (
                currentElement instanceof HTMLElement
                && targetElement instanceof HTMLElement
            ) {
                currentElement.replaceWith(targetElement);
            }
        });
    }

    function synchronizeThemePreference(parsedDocument) {
        const preference = (
            parsedDocument.documentElement.dataset.themePreference
            || "sistema"
        );

        document.documentElement.dataset.themePreference = preference;

        if (window.BFGendaTheme?.applyPreference) {
            window.BFGendaTheme.applyPreference(
                preference,
                {persist: true}
            );
        }
    }

    async function refreshMain(
        rawUrl = window.location.href,
        {preserveScroll = true} = {}
    ) {
        const currentMain = document.querySelector("#app-main-content");
        const targetUrl = new URL(rawUrl, window.location.href);

        if (!(currentMain instanceof HTMLElement)) {
            window.location.assign(targetUrl);
            return;
        }

        const windowPosition = {
            x: window.scrollX,
            y: window.scrollY,
        };
        const nestedPositions = captureNestedScroll();
        currentMain.classList.add("content-refreshing");

        try {
            const response = await fetch(targetUrl, {
                method: "GET",
                headers: {"X-Requested-With": "XMLHttpRequest"},
                credentials: "same-origin",
            });

            if (!response.ok) {
                throw new Error(`Error HTTP ${response.status}`);
            }

            const html = await response.text();
            const parsed = new DOMParser().parseFromString(html, "text/html");
            const newMain = parsed.querySelector("#app-main-content");

            if (!(newMain instanceof HTMLElement)) {
                throw new Error("La respuesta no contiene el contenido principal.");
            }

            const incomingSwipeSurface = newMain.querySelector(
                "[data-filter-swipe-surface]"
            );
            const incomingSwipeDirection = filterSwipeDirection;

            if (
                incomingSwipeSurface instanceof HTMLElement
                && incomingSwipeDirection
            ) {
                incomingSwipeSurface.classList.add(
                    `filter-swipe-enter-${incomingSwipeDirection}`
                );
            }

            await synchronizePageStyles(parsed);
            synchronizeThemePreference(parsed);
            currentMain.replaceWith(newMain);
            synchronizeApplicationShell(parsed);
            filterSwipeDirection = null;

            if (parsed.title) {
                document.title = parsed.title;
            }

            window.requestAnimationFrame(() => {
                if (
                    incomingSwipeSurface instanceof HTMLElement
                    && incomingSwipeDirection
                ) {
                    window.requestAnimationFrame(() => {
                        incomingSwipeSurface.classList.remove(
                            `filter-swipe-enter-${incomingSwipeDirection}`
                        );
                    });
                }

                const targetId = targetUrl.hash
                    ? decodeURIComponent(targetUrl.hash.slice(1))
                    : "";
                const targetElement = targetId
                    ? document.getElementById(targetId)
                    : null;

                if (preserveScroll) {
                    restoreNestedScroll(nestedPositions);
                }

                if (targetElement instanceof HTMLElement) {
                    targetElement.scrollIntoView({
                        behavior: "smooth",
                        block: "center",
                    });
                } else if (preserveScroll) {
                    window.scrollTo(windowPosition.x, windowPosition.y);
                } else {
                    window.scrollTo({top: 0, left: 0, behavior: "auto"});
                }
            });

            document.dispatchEvent(new CustomEvent("agende:content-updated"));
        } catch (error) {
            console.error("No se pudo actualizar la pantalla:", error);
            filterSwipeDirection = null;
            filterSwipeInProgress = false;
            currentMain.classList.remove("content-refreshing");
            window.location.assign(targetUrl);
        }
    }

    async function navigate(rawUrl, {replace = false} = {}) {
        const url = new URL(rawUrl, window.location.href);
        const preserveScroll = url.pathname === window.location.pathname;

        if (replace) {
            window.history.replaceState({}, "", url);
        } else {
            window.history.pushState({}, "", url);
        }

        await refreshMain(url, {preserveScroll});
    }

    function loadingMarkup() {
        return '<div class="modal-loading">Cargando…</div>';
    }

    function errorMarkup() {
        return `
            <div class="modal-request-error">
                <strong>No se pudo cargar el contenido</strong>
                <p>Comprueba que el servidor continúe funcionando e inténtalo nuevamente.</p>
            </div>
        `;
    }

    function shouldAutoFocusForm() {
        const finePointer = window.matchMedia(
            "(hover: hover) and (pointer: fine)"
        ).matches;

        return finePointer && window.innerWidth > 760;
    }

    function focusFirstField() {
        if (!shouldAutoFocusForm()) {
            return;
        }

        window.requestAnimationFrame(() => {
            const firstField = modalContent?.querySelector(
                "[data-autofocus], input:not([type='hidden']), textarea, select, button, a"
            );

            if (firstField instanceof HTMLElement) {
                firstField.focus({preventScroll: true});
            }
        });
    }

    function animateLoadedModalContent() {
        if (!(modalContent instanceof HTMLElement)) {
            return;
        }

        modalContent.classList.remove("modal-content-entering");
        void modalContent.offsetWidth;
        modalContent.classList.add("modal-content-entering");

        window.setTimeout(() => {
            modalContent.classList.remove("modal-content-entering");
        }, 340);
    }

    function openDialog() {
        if (dialog instanceof HTMLDialogElement && !dialog.open) {
            dialog.showModal();
        }
    }

    function closeDialog() {
        if (dialog instanceof HTMLDialogElement && dialog.open) {
            dialog.close();
        }
    }

    async function openModal(rawUrl, trigger = null) {
        if (
            !(dialog instanceof HTMLDialogElement)
            || !(modalContent instanceof HTMLElement)
        ) {
            window.location.assign(rawUrl);
            return;
        }

        modalTrigger = trigger instanceof HTMLElement ? trigger : document.activeElement;
        modalContent.innerHTML = loadingMarkup();
        openDialog();

        try {
            const url = withReturnUrl(rawUrl);
            const response = await fetch(url, {
                method: "GET",
                headers: {"X-Requested-With": "XMLHttpRequest"},
                credentials: "same-origin",
            });
            const data = await response.json();

            if (!response.ok || !data.html) {
                throw new Error("La respuesta no contiene contenido para el modal.");
            }

            modalContent.innerHTML = data.html;
            animateLoadedModalContent();
            focusFirstField();
        } catch (error) {
            console.error("No se pudo abrir el modal:", error);
            modalContent.innerHTML = errorMarkup();
        }
    }


    async function openAutomaticModal() {
        const trigger = document.querySelector("[data-auto-modal-url]");

        if (!(trigger instanceof HTMLElement)) {
            return;
        }

        const url = trigger.dataset.autoModalUrl;
        trigger.remove();

        if (url) {
            await openModal(url, trigger);
        }
    }

    function calendarTargetUrl(baseUrl, dateValue) {
        const url = new URL(baseUrl, window.location.href);
        const calendarContent = document.querySelector("[data-calendar-view]");

        if (!(calendarContent instanceof HTMLElement) || !dateValue) {
            return url;
        }

        const view = calendarContent.dataset.calendarView || "mes";
        url.searchParams.set("vista", view);
        url.searchParams.set("dia", dateValue);

        if (view === "mes") {
            url.searchParams.set("mes", dateValue.slice(0, 7));
        } else {
            url.searchParams.delete("mes");
        }

        return url;
    }

    async function submitModalForm(form) {
        const buttons = Array.from(form.querySelectorAll("button"));
        const submitButton = form.querySelector("button[type='submit']");
        const originalText = submitButton?.textContent || "";

        buttons.forEach((button) => {
            button.disabled = true;
        });

        if (submitButton instanceof HTMLButtonElement) {
            submitButton.textContent = "Guardando…";
        }

        try {
            const response = await fetch(form.action, {
                method: "POST",
                headers: {"X-Requested-With": "XMLHttpRequest"},
                body: new FormData(form),
                credentials: "same-origin",
            });
            const data = await response.json();

            if (data.ok) {
                closeDialog();

                if (data.hard_reload) {
                    showToast(data.message || "Acción completada.");
                    const destination = data.redirect_url || window.location.href;
                    window.setTimeout(() => {
                        window.location.assign(destination);
                    }, 350);
                    return;
                }

                const target = calendarTargetUrl(
                    data.refresh_url || window.location.href,
                    data.date
                );
                const historyTarget = calendarTargetUrl(
                    data.history_url || target,
                    data.date
                );

                window.history.replaceState({}, "", historyTarget);
                await refreshMain(target);
                showToast(data.message || "Cambios guardados.");
                return;
            }

            if (data.html) {
                modalContent.innerHTML = data.html;
                animateLoadedModalContent();
                focusFirstField();
                return;
            }

            throw new Error("La respuesta del formulario no es válida.");
        } catch (error) {
            console.error("No se pudo guardar el formulario:", error);
            modalContent.innerHTML = errorMarkup();
        } finally {
            buttons.forEach((button) => {
                button.disabled = false;
            });

            if (submitButton instanceof HTMLButtonElement && originalText) {
                submitButton.textContent = originalText;
            }
        }
    }

    async function submitActionForm(form) {
        const submitButton = form.querySelector("button[type='submit']");
        const originalText = submitButton?.textContent || "";
        const formData = new FormData(form);

        if (!formData.has("return_url")) {
            formData.append("return_url", currentRelativeUrl());
        }

        if (submitButton instanceof HTMLButtonElement) {
            submitButton.disabled = true;
        }

        try {
            const response = await fetch(form.action, {
                method: "POST",
                headers: {"X-Requested-With": "XMLHttpRequest"},
                body: formData,
                credentials: "same-origin",
            });
            const data = await response.json();

            if (!response.ok || !data.ok) {
                throw new Error(data.message || "La acción no pudo completarse.");
            }

            const target = data.refresh_url || window.location.href;
            window.history.replaceState({}, "", data.history_url || target);
            await refreshMain(target);
            showToast(data.message || "Acción completada.");
        } catch (error) {
            console.error("No se pudo completar la acción:", error);
            showToast(
                error instanceof Error
                    ? error.message
                    : "No se pudo completar la acción.",
                "error"
            );
        } finally {
            if (submitButton instanceof HTMLButtonElement) {
                submitButton.disabled = false;
                submitButton.textContent = originalText;
            }
        }
    }

    document.addEventListener("click", (event) => {
        if (!(event.target instanceof Element)) {
            return;
        }

        const modalLink = event.target.closest("[data-modal-url]");

        if (modalLink instanceof HTMLAnchorElement) {
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

            event.preventDefault();
            openModal(modalLink.dataset.modalUrl || modalLink.href, modalLink);
            return;
        }

        const appLink = event.target.closest("[data-app-link]");

        if (appLink instanceof HTMLAnchorElement) {
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

            event.preventDefault();
            closeDialog();
            navigate(appLink.href);
            return;
        }

        const closeTrigger = event.target.closest("[data-modal-close]");

        if (closeTrigger) {
            if (dialog instanceof HTMLDialogElement && dialog.open) {
                event.preventDefault();
                closeDialog();
            }
        }
    });

    document.addEventListener("submit", (event) => {
        const form = event.target;

        if (!(form instanceof HTMLFormElement)) {
            return;
        }

        if (form.classList.contains("js-ajax-form")) {
            event.preventDefault();
            submitModalForm(form);
            return;
        }

        if (form.matches("[data-ajax-form]")) {
            event.preventDefault();
            submitActionForm(form);
        }
    });

    if (dialog instanceof HTMLDialogElement) {
        dialog.addEventListener("click", (event) => {
            if (event.target === dialog) {
                closeDialog();
            }
        });

        dialog.addEventListener("close", () => {
            modalContent?.replaceChildren();

            if (modalTrigger instanceof HTMLElement && modalTrigger.isConnected) {
                modalTrigger.focus({preventScroll: true});
            }

            modalTrigger = null;
        });
    }

    window.addEventListener("popstate", () => {
        refreshMain(window.location.href);
    });

    let filterSwipeStart = null;
    const mobileFilterMedia = window.matchMedia("(max-width: 760px)");
    const reducedMotionMedia = window.matchMedia(
        "(prefers-reduced-motion: reduce)"
    );

    const resetFilterSwipe = () => {
        filterSwipeStart = null;
    };

    document.addEventListener(
        "touchstart",
        (event) => {
            const target = event.target;

            if (
                filterSwipeInProgress
                || !mobileFilterMedia.matches
                || event.touches.length !== 1
                || !(target instanceof Element)
                || target.closest(
                    "a, button, input, select, textarea, label, summary, "
                    + "[contenteditable='true'], [data-no-filter-swipe]"
                )
            ) {
                resetFilterSwipe();
                return;
            }

            const surface = target.closest("[data-filter-swipe-surface]");

            if (!(surface instanceof HTMLElement)) {
                resetFilterSwipe();
                return;
            }

            const touch = event.touches[0];
            filterSwipeStart = {
                surface,
                x: touch.clientX,
                y: touch.clientY,
                startedAt: performance.now(),
            };
        },
        {passive: true}
    );

    document.addEventListener(
        "touchend",
        (event) => {
            if (
                !filterSwipeStart
                || event.changedTouches.length !== 1
            ) {
                resetFilterSwipe();
                return;
            }

            const {surface, x, y, startedAt} = filterSwipeStart;
            const touch = event.changedTouches[0];
            const deltaX = touch.clientX - x;
            const deltaY = touch.clientY - y;
            const elapsed = performance.now() - startedAt;

            resetFilterSwipe();

            if (
                !surface.isConnected
                || Math.abs(deltaX) < 64
                || Math.abs(deltaX) < Math.abs(deltaY) * 1.35
                || elapsed > 900
            ) {
                return;
            }

            const main = surface.closest("#app-main-content");
            const filters = main?.querySelector("[data-filter-swipe]");

            if (!(filters instanceof HTMLElement)) {
                return;
            }

            const links = Array.from(filters.querySelectorAll("a[href]"));
            const activeIndex = links.findIndex((link) => (
                link.classList.contains("active")
            ));
            const direction = deltaX < 0 ? "next" : "previous";
            const targetIndex = activeIndex + (direction === "next" ? 1 : -1);
            const targetLink = links[targetIndex];

            if (!(targetLink instanceof HTMLAnchorElement)) {
                return;
            }

            filterSwipeInProgress = true;
            filterSwipeDirection = direction;
            surface.setAttribute("aria-busy", "true");
            surface.classList.add(`filter-swipe-out-${direction}`);

            window.setTimeout(() => {
                navigate(targetLink.href).finally(() => {
                    filterSwipeInProgress = false;
                });
            }, reducedMotionMedia.matches ? 0 : 130);
        },
        {passive: true}
    );

    document.addEventListener("touchcancel", resetFilterSwipe, {passive: true});

    document.addEventListener("agende:content-updated", openAutomaticModal);

    window.AgendeApp = {
        refreshMain,
        navigate,
        showToast,
        openModal,
    };

    openAutomaticModal();
});

/* ============================================================
   FASE A1 — MENÚS MÓVILES Y FILTROS ACTIVOS
   ============================================================ */

(() => {
    "use strict";

    const closeMobileMenus = (exception = null) => {
        document
            .querySelectorAll("details[data-mobile-menu][open]")
            .forEach((menu) => {
                if (menu !== exception) {
                    menu.removeAttribute("open");
                }
            });
    };

    document.addEventListener(
        "toggle",
        (event) => {
            const menu = event.target.closest(
                "details[data-mobile-menu]"
            );

            if (menu && menu.open) {
                closeMobileMenus(menu);
            }
        },
        true
    );

    document.addEventListener("click", (event) => {
        const target = event.target;

        if (!(target instanceof Element)) {
            return;
        }

        const menuLink = target.closest(
            "[data-mobile-menu-link]"
        );

        if (menuLink) {
            closeMobileMenus();
            return;
        }

        if (!target.closest("details[data-mobile-menu]")) {
            closeMobileMenus();
        }
    });

    const centerActiveFilter = (container) => {
        const activeFilter = container.querySelector(".active");

        if (!activeFilter) {
            return;
        }

        const containerRect =
            container.getBoundingClientRect();
        const activeRect =
            activeFilter.getBoundingClientRect();
        const desiredPosition =
            container.scrollLeft
            + activeRect.left
            - containerRect.left
            - (container.clientWidth - activeRect.width) / 2;
        const maximumPosition = Math.max(
            0,
            container.scrollWidth - container.clientWidth
        );

        container.scrollTo({
            left: Math.min(
                maximumPosition,
                Math.max(0, desiredPosition)
            ),
            behavior: "auto",
        });
    };

    const alignActiveFilters = () => {
        document
            .querySelectorAll(".task-filters, .event-filters")
            .forEach(centerActiveFilter);
    };

    document.addEventListener(
        "agende:content-updated",
        alignActiveFilters
    );

    if (document.readyState === "loading") {
        document.addEventListener(
            "DOMContentLoaded",
            alignActiveFilters,
            {once: true}
        );
    } else {
        alignActiveFilters();
    }
})();
