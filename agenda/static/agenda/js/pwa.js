"use strict";

(() => {
    if (!("serviceWorker" in navigator)) {
        return;
    }

    window.addEventListener("load", () => {
        navigator.serviceWorker
            .register("/service-worker.js", {
                scope: "/"
            })
            .catch((error) => {
                console.error(
                    "No se pudo registrar la PWA de BFGenda.",
                    error
                );
            });
    });
})();
