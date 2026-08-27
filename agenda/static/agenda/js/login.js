"use strict";

document.addEventListener("DOMContentLoaded", () => {
    const autofocusTarget = document.querySelector("[data-autofocus='true']");
    const desktopPointer = window.matchMedia(
        "(hover: hover) and (pointer: fine)"
    );

    if (
        autofocusTarget instanceof HTMLElement
        && desktopPointer.matches
        && window.innerWidth > 760
    ) {
        autofocusTarget.focus({ preventScroll: true });
    }

    const dialog = document.querySelector("#shutdown-confirmation");
    const openButton = document.querySelector("[data-shutdown-open]");

    if (
        !(dialog instanceof HTMLDialogElement)
        || !(openButton instanceof HTMLButtonElement)
    ) {
        return;
    }

    const closeButtons = dialog.querySelectorAll("[data-shutdown-close]");

    openButton.addEventListener("click", () => {
        if (!dialog.open) {
            dialog.showModal();
        }
    });

    closeButtons.forEach((button) => {
        button.addEventListener("click", () => {
            if (dialog.open) {
                dialog.close();
            }
        });
    });

    dialog.addEventListener("click", (event) => {
        if (event.target === dialog) {
            dialog.close();
        }
    });
});
