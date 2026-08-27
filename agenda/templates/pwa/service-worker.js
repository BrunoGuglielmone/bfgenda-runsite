{% load static %}
"use strict";

const CACHE_VERSION = "bfgenda-public-v3";
const OFFLINE_URL = "/sin-conexion/";

const PUBLIC_ASSETS = [
    OFFLINE_URL,
    "{% static 'agenda/img/branding/bfgenda-simbolo-xl-192.png' %}",
    "{% static 'agenda/img/branding/bfgenda-simbolo-xl-512.png' %}"
];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches
            .open(CACHE_VERSION)
            .then((cache) => cache.addAll(PUBLIC_ASSETS))
    );

    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches
            .keys()
            .then((keys) =>
                Promise.all(
                    keys
                        .filter((key) => key !== CACHE_VERSION)
                        .map((key) => caches.delete(key))
                )
            )
            .then(() => self.clients.claim())
    );
});

self.addEventListener("fetch", (event) => {
    const request = event.request;

    if (request.method !== "GET") {
        return;
    }

    const url = new URL(request.url);

    if (url.origin !== self.location.origin) {
        return;
    }

    if (request.mode === "navigate") {
        event.respondWith(
            fetch(request).catch(() => caches.match(OFFLINE_URL))
        );
        return;
    }

    if (!url.pathname.startsWith("/static/")) {
        return;
    }

    event.respondWith(
        caches.match(request).then((cachedResponse) => {
            if (cachedResponse) {
                return cachedResponse;
            }

            return fetch(request).then((networkResponse) => {
                if (
                    !networkResponse ||
                    networkResponse.status !== 200 ||
                    networkResponse.type !== "basic"
                ) {
                    return networkResponse;
                }

                const copy = networkResponse.clone();

                caches
                    .open(CACHE_VERSION)
                    .then((cache) => cache.put(request, copy));

                return networkResponse;
            });
        })
    );
});

self.addEventListener("push", (event) => {
    let payload = {};

    if (event.data) {
        try {
            payload = event.data.json();
        } catch (error) {
            payload = {
                body: event.data.text()
            };
        }
    }

    const icon = (
        payload.icon
        || "{% static 'agenda/img/branding/bfgenda-simbolo-xl-192.png' %}"
    );

    event.waitUntil(
        self.registration.showNotification(
            payload.title || "BFGenda",
            {
                body: payload.body || "Tienes un recordatorio pendiente.",
                icon,
                badge: icon,
                tag: payload.tag || "bfgenda-recordatorio",
                renotify: false,
                data: {
                    url: payload.url || "/"
                }
            }
        )
    );
});

self.addEventListener("notificationclick", (event) => {
    event.notification.close();

    const targetUrl =
        event.notification.data?.url || "/";

    event.waitUntil(
        clients
            .matchAll({
                type: "window",
                includeUncontrolled: true
            })
            .then((windowClients) => {
                for (const client of windowClients) {
                    const clientUrl = new URL(client.url);

                    if (
                        clientUrl.origin === self.location.origin
                        && "focus" in client
                    ) {
                        client.navigate(targetUrl);
                        return client.focus();
                    }
                }

                return clients.openWindow(targetUrl);
            })
    );
});
