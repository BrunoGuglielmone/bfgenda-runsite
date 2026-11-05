"use strict";

(() => {
    const initializedPanels = new WeakSet();
    const CHECK_INTERVAL_MS = 60 * 1000;
    const STORAGE_PREFIX = "bfgenda-reminder:";
    let reminderCheckInProgress = false;
    let reminderIntervalId = null;

    function showToast(message, type = "success") {
        if (
            window.AgendeApp
            && typeof window.AgendeApp.showToast === "function"
        ) {
            window.AgendeApp.showToast(message, type);
        }
    }

    function notificationsSupported() {
        return (
            "Notification" in window
            && "serviceWorker" in navigator
        );
    }

    function pushSupported() {
        return (
            notificationsSupported()
            && "PushManager" in window
        );
    }

    function urlBase64ToUint8Array(value) {
        const padding = "=".repeat((4 - value.length % 4) % 4);
        const base64 = (value + padding)
            .replace(/-/g, "+")
            .replace(/_/g, "/");
        const rawData = window.atob(base64);

        return Uint8Array.from(
            rawData,
            (character) => character.charCodeAt(0)
        );
    }

    function getCookie(name) {
        const prefix = `${name}=`;
        const cookies = document.cookie ? document.cookie.split(";") : [];

        for (const rawCookie of cookies) {
            const cookie = rawCookie.trim();

            if (cookie.startsWith(prefix)) {
                return decodeURIComponent(cookie.slice(prefix.length));
            }
        }

        return "";
    }

    async function postJson(url, payload) {
        const response = await fetch(url, {
            method: "POST",
            credentials: "same-origin",
            cache: "no-store",
            headers: {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-CSRFToken": getCookie("csrftoken")
            },
            body: JSON.stringify(payload)
        });
        const data = await response.json().catch(() => null);

        if (!response.ok || !data || data.ok !== true) {
            throw new Error(
                data?.error || `El servidor devolvi\u00f3 ${response.status}.`
            );
        }

        return data;
    }

    function pushConfiguration(panel) {
        return {
            enabled: panel.dataset.pushServerEnabled === "true",
            publicKey: panel.dataset.pushPublicKey || "",
            subscribeUrl: panel.dataset.pushSubscribeUrl || "",
            unsubscribeUrl: panel.dataset.pushUnsubscribeUrl || "",
            testUrl: panel.dataset.pushTestUrl || ""
        };
    }

    async function ensurePushSubscription(panel) {
        const config = pushConfiguration(panel);

        if (
            !pushSupported()
            || !config.enabled
            || !config.publicKey
            || !config.subscribeUrl
        ) {
            throw new Error(
                "Web Push todav\u00eda no est\u00e1 configurado en el servidor."
            );
        }

        const registration = await getRegistration();
        let subscription = await registration.pushManager.getSubscription();

        if (!subscription) {
            subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: urlBase64ToUint8Array(
                    config.publicKey
                )
            });
        }

        await postJson(config.subscribeUrl, subscription.toJSON());
        return subscription;
    }

    async function getRegistration() {
        const existingRegistration =
            await navigator.serviceWorker.getRegistration("/");

        if (existingRegistration) {
            return existingRegistration;
        }

        return navigator.serviceWorker.ready;
    }

    function getNotificationIcon() {
        return (
            document.body?.dataset.notificationIcon
            || "/static/agenda/img/branding/"
                + "bfgenda-simbolo-xl-192.png"
        );
    }

    function reminderStorageKey(reminder) {
        return `${STORAGE_PREFIX}${reminder.tag}`;
    }

    function wasReminderShown(reminder) {
        try {
            return (
                window.localStorage.getItem(
                    reminderStorageKey(reminder)
                ) === "shown"
            );
        } catch (error) {
            console.warn(
                "No se pudo leer el historial de recordatorios:",
                error
            );
            return false;
        }
    }

    function markReminderAsShown(reminder) {
        try {
            window.localStorage.setItem(
                reminderStorageKey(reminder),
                "shown"
            );
        } catch (error) {
            console.warn(
                "No se pudo guardar el recordatorio mostrado:",
                error
            );
        }
    }

    async function showReminder(registration, reminder) {
        if (
            !reminder
            || typeof reminder.tag !== "string"
            || typeof reminder.title !== "string"
            || wasReminderShown(reminder)
        ) {
            return;
        }

        const icon = getNotificationIcon();

        await registration.showNotification(
            reminder.title,
            {
                body: reminder.body || "",
                icon,
                badge: icon,
                tag: reminder.tag,
                renotify: false,
                data: {
                    url: reminder.url || "/"
                }
            }
        );

        markReminderAsShown(reminder);
    }

    async function checkPendingReminders() {
        if (
            reminderCheckInProgress
            || document.visibilityState !== "visible"
            || !notificationsSupported()
            || Notification.permission !== "granted"
        ) {
            return;
        }

        const endpoint = document.body?.dataset.remindersUrl;

        if (!endpoint) {
            return;
        }

        reminderCheckInProgress = true;

        try {
            const response = await fetch(endpoint, {
                method: "GET",
                credentials: "same-origin",
                cache: "no-store",
                headers: {
                    "Accept": "application/json"
                }
            });

            if (
                response.status === 401
                || response.status === 403
            ) {
                return;
            }

            if (!response.ok) {
                throw new Error(
                    `El endpoint devolvió ${response.status}.`
                );
            }

            const payload = await response.json();

            if (
                !payload
                || payload.ok !== true
                || !Array.isArray(payload.reminders)
            ) {
                throw new Error(
                    "La respuesta de recordatorios no es válida."
                );
            }

            const registration = await getRegistration();

            for (const reminder of payload.reminders) {
                await showReminder(registration, reminder);
            }
        } catch (error) {
            console.error(
                "No se pudieron consultar los recordatorios:",
                error
            );
        } finally {
            reminderCheckInProgress = false;
        }
    }

    function startReminderChecks() {
        if (reminderIntervalId !== null) {
            return;
        }

        checkPendingReminders();

        reminderIntervalId = window.setInterval(
            checkPendingReminders,
            CHECK_INTERVAL_MS
        );
    }

    function initializePanel(panel) {
        if (
            !(panel instanceof HTMLElement)
            || initializedPanels.has(panel)
        ) {
            return;
        }

        initializedPanels.add(panel);

        const status = panel.querySelector(
            "[data-notification-status]"
        );
        const enableButton = panel.querySelector(
            "[data-notification-enable]"
        );
        const testButton = panel.querySelector(
            "[data-notification-test]"
        );
        const disableButton = panel.querySelector(
            "[data-notification-disable]"
        );

        if (
            !(status instanceof HTMLElement)
            || !(enableButton instanceof HTMLButtonElement)
            || !(testButton instanceof HTMLButtonElement)
            || !(disableButton instanceof HTMLButtonElement)
        ) {
            return;
        }

        async function renderState() {
            enableButton.hidden = true;
            testButton.hidden = true;
            disableButton.hidden = true;

            if (!notificationsSupported()) {
                status.textContent =
                    "Este navegador no admite notificaciones.";
                status.dataset.state = "unsupported";
                return;
            }

            if (Notification.permission === "granted") {
                testButton.hidden = false;

                const config = pushConfiguration(panel);

                if (!pushSupported() || !config.enabled) {
                    status.textContent = (
                        "Avisos locales activados; Web Push no est\u00e1 "
                        + "disponible en este servidor."
                    );
                    status.dataset.state = "pending";
                    return;
                }

                const registration = await getRegistration();
                const subscription =
                    await registration.pushManager.getSubscription();

                if (subscription) {
                    status.textContent = (
                        "Notificaciones en segundo plano activadas"
                    );
                    status.dataset.state = "enabled";
                    disableButton.hidden = false;
                    return;
                }

                status.textContent = (
                    "Permiso concedido; falta registrar este dispositivo."
                );
                status.dataset.state = "pending";
                enableButton.textContent = "Completar activaci\u00f3n";
                enableButton.hidden = false;
                return;
            }

            if (Notification.permission === "denied") {
                status.textContent =
                    "Notificaciones bloqueadas en el navegador";
                status.dataset.state = "blocked";
                return;
            }

            status.textContent = "Notificaciones no activadas";
            status.dataset.state = "pending";
            enableButton.hidden = false;
        }

        enableButton.addEventListener("click", async () => {
            enableButton.disabled = true;

            try {
                let permission = Notification.permission;

                if (permission === "default") {
                    permission = await Notification.requestPermission();
                }

                if (permission === "granted") {
                    await ensurePushSubscription(panel);
                    await renderState();
                    showToast(
                        "Las notificaciones en segundo plano quedaron activadas."
                    );
                    checkPendingReminders();
                } else if (permission === "denied") {
                    await renderState();
                    showToast(
                        "El navegador bloque\u00f3 las notificaciones.",
                        "error"
                    );
                }
            } catch (error) {
                console.error(
                    "No se pudo solicitar el permiso:",
                    error
                );
                showToast(
                    "No se pudo solicitar el permiso.",
                    "error"
                );
            } finally {
                enableButton.disabled = false;
            }
        });

        testButton.addEventListener("click", async () => {
            testButton.disabled = true;

            try {
                if (Notification.permission !== "granted") {
                    await renderState();
                    return;
                }

                const registration = await getRegistration();
                const config = pushConfiguration(panel);
                const subscription = pushSupported()
                    ? await registration.pushManager.getSubscription()
                    : null;

                if (subscription && config.enabled && config.testUrl) {
                    await postJson(
                        config.testUrl,
                        {endpoint: subscription.endpoint}
                    );
                    showToast(
                        "Notificaci\u00f3n Push de prueba enviada."
                    );
                    return;
                }

                const icon = getNotificationIcon();

                await registration.showNotification(
                    "BFGenda",
                    {
                        body: (
                            "Las notificaciones funcionan correctamente "
                            + "en este dispositivo."
                        ),
                        icon,
                        badge: icon,
                        tag: "bfgenda-prueba",
                        renotify: true,
                        data: {
                            url: "/configuracion/"
                        }
                    }
                );

                showToast(
                    "Notificaci\u00f3n de prueba enviada."
                );
            } catch (error) {
                console.error(
                    "No se pudo mostrar la notificaci\u00f3n:",
                    error
                );
                showToast(
                    (
                        error instanceof Error && error.message
                            ? error.message
                            : "No se pudo mostrar la notificaci\u00f3n."
                    ),
                    "error"
                );
            } finally {
                testButton.disabled = false;
            }
        });

        disableButton.addEventListener("click", async () => {
            disableButton.disabled = true;

            try {
                const registration = await getRegistration();
                const subscription = pushSupported()
                    ? await registration.pushManager.getSubscription()
                    : null;
                const config = pushConfiguration(panel);

                if (subscription) {
                    if (config.unsubscribeUrl) {
                        await postJson(
                            config.unsubscribeUrl,
                            {endpoint: subscription.endpoint}
                        );
                    }

                    await subscription.unsubscribe();
                }

                await renderState();
                showToast(
                    "Las notificaciones se desactivaron en este dispositivo."
                );
            } catch (error) {
                console.error(
                    "No se pudo desactivar Web Push:",
                    error
                );
                showToast(
                    "No se pudieron desactivar las notificaciones.",
                    "error"
                );
            } finally {
                disableButton.disabled = false;
            }
        });

        renderState().catch((error) => {
            console.error(
                "No se pudo comprobar el estado de Web Push:",
                error
            );
            status.textContent = "No se pudo comprobar Web Push.";
            status.dataset.state = "blocked";
        });
    }

    function initializeNotificationPanels() {
        document
            .querySelectorAll("[data-notification-panel]")
            .forEach(initializePanel);
    }

    document.addEventListener(
        "DOMContentLoaded",
        () => {
            initializeNotificationPanels();
            startReminderChecks();
        }
    );

    document.addEventListener(
        "agende:content-updated",
        initializeNotificationPanels
    );

    document.addEventListener(
        "visibilitychange",
        () => {
            if (document.visibilityState === "visible") {
                checkPendingReminders();
            }
        }
    );

    window.addEventListener(
        "focus",
        checkPendingReminders
    );
})();


(() => {
    const CHECK_INTERVAL_MS = 60 * 1000;
    const STORAGE_PREFIX = "bfgenda-past-event:";
    let checkInProgress = false;
    let intervalId = null;

    function storageKey(eventData) {
        return `${STORAGE_PREFIX}${eventData.tag}`;
    }

    function wasShown(eventData) {
        try {
            return (
                window.localStorage.getItem(
                    storageKey(eventData)
                ) === "shown"
            );
        } catch (error) {
            console.warn(
                "No se pudo consultar el historial de eventos pasados:",
                error
            );
            return false;
        }
    }

    function markAsShown(eventData) {
        try {
            window.localStorage.setItem(
                storageKey(eventData),
                "shown"
            );
        } catch (error) {
            console.warn(
                "No se pudo registrar el aviso de evento pasado:",
                error
            );
        }
    }

    function anotherModalIsOpen() {
        const dialog = document.querySelector("#app-modal");

        return (
            dialog instanceof HTMLDialogElement
            && dialog.open
        );
    }

    async function checkPastEvents() {
        if (
            checkInProgress
            || document.visibilityState !== "visible"
            || anotherModalIsOpen()
        ) {
            return;
        }

        const endpoint =
            document.body?.dataset.pastEventsUrl;

        if (
            !endpoint
            || !window.AgendeApp
            || typeof window.AgendeApp.openModal !== "function"
        ) {
            return;
        }

        checkInProgress = true;

        try {
            const response = await fetch(endpoint, {
                method: "GET",
                credentials: "same-origin",
                cache: "no-store",
                headers: {
                    "Accept": "application/json"
                }
            });

            if (
                response.status === 401
                || response.status === 403
            ) {
                return;
            }

            if (!response.ok) {
                throw new Error(
                    `El endpoint devolvió ${response.status}.`
                );
            }

            const payload = await response.json();
            const eventData = payload?.event;

            if (
                payload?.ok !== true
                || !eventData
                || typeof eventData.tag !== "string"
                || typeof eventData.modal_url !== "string"
                || wasShown(eventData)
            ) {
                return;
            }

            markAsShown(eventData);

            await window.AgendeApp.openModal(
                eventData.modal_url
            );
        } catch (error) {
            console.error(
                "No se pudo comprobar si hay eventos pasados:",
                error
            );
        } finally {
            checkInProgress = false;
        }
    }

    function startChecks() {
        if (intervalId !== null) {
            return;
        }

        checkPastEvents();

        intervalId = window.setInterval(
            checkPastEvents,
            CHECK_INTERVAL_MS
        );
    }

    document.addEventListener(
        "DOMContentLoaded",
        startChecks
    );

    document.addEventListener(
        "agende:content-updated",
        checkPastEvents
    );

    document.addEventListener(
        "visibilitychange",
        () => {
            if (document.visibilityState === "visible") {
                checkPastEvents();
            }
        }
    );

    window.addEventListener(
        "focus",
        checkPastEvents
    );
})();
