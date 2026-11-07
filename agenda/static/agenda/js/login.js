"use strict";

document.addEventListener("DOMContentLoaded", () => {
    const desktopPointer = window.matchMedia(
        "(hover: hover) and (pointer: fine)"
    );
    const panelButtons = document.querySelectorAll("[data-login-panel-target]");
    const panels = document.querySelectorAll("[data-login-panel]");
    const usernameInputs = document.querySelectorAll(
        "[data-remembered-username]"
    );
    const rememberToggle = document.querySelector(
        "[data-remember-username-toggle]"
    );
    const rememberedUsernameKey = "bfgenda-remembered-username";

    function storedUsername() {
        try {
            return window.localStorage.getItem(rememberedUsernameKey) || "";
        } catch (error) {
            return "";
        }
    }

    function persistUsername(value) {
        try {
            if (value) {
                window.localStorage.setItem(rememberedUsernameKey, value);
            } else {
                window.localStorage.removeItem(rememberedUsernameKey);
            }
        } catch (error) {
            // El acceso sigue funcionando aunque el navegador bloquee storage.
        }
    }

    const rememberedUsername = storedUsername();

    if (rememberedUsername) {
        usernameInputs.forEach((input) => {
            if (input instanceof HTMLInputElement && !input.value) {
                input.value = rememberedUsername;
            }
        });

        if (rememberToggle instanceof HTMLInputElement) {
            rememberToggle.checked = true;
        }
    }

    usernameInputs.forEach((input) => {
        input.addEventListener("change", () => {
            if (!(input instanceof HTMLInputElement) || !input.value.trim()) {
                return;
            }

            usernameInputs.forEach((otherInput) => {
                if (
                    otherInput instanceof HTMLInputElement
                    && !otherInput.value
                ) {
                    otherInput.value = input.value.trim();
                }
            });
        });
    });

    document.querySelectorAll(".login-form").forEach((form) => {
        form.addEventListener("submit", () => {
            if (!(rememberToggle instanceof HTMLInputElement)) {
                return;
            }

            const username = form.querySelector("[data-remembered-username]");

            if (rememberToggle.checked && username instanceof HTMLInputElement) {
                persistUsername(username.value.trim());
            } else if (!rememberToggle.checked) {
                persistUsername("");
            }
        });
    });

    function focusPanel(panel) {
        if (!desktopPointer.matches || window.innerWidth <= 760) {
            return;
        }

        const target = panel.querySelector(
            "[data-quick-autofocus], [data-autofocus='true']"
        );

        if (target instanceof HTMLElement) {
            target.focus({preventScroll: true});
        }
    }

    function showPanel(name, {updateUrl = true} = {}) {
        let activePanel = null;

        panels.forEach((panel) => {
            const selected = panel.dataset.loginPanel === name;
            panel.hidden = !selected;

            if (selected) {
                activePanel = panel;
            }
        });

        panelButtons.forEach((button) => {
            const selected = button.dataset.loginPanelTarget === name;
            button.classList.toggle("is-active", selected);

            if (button.closest(".login-navigation-menu")) {
                button.setAttribute("aria-selected", String(selected));
            }
        });

        document.body.dataset.loginInitialPanel = name;

        if (updateUrl) {
            const url = new URL(window.location.href);
            url.searchParams.set("panel", name);
            window.history.replaceState({}, "", url);
        }

        if (activePanel instanceof HTMLElement) {
            focusPanel(activePanel);
        }
    }

    panelButtons.forEach((button) => {
        button.addEventListener("click", () => {
            showPanel(button.dataset.loginPanelTarget || "login");
        });
    });

    const initialPanelName = document.body.dataset.loginInitialPanel || "login";
    const initialPanel = document.querySelector(
        `[data-login-panel="${initialPanelName}"]`
    );

    if (
        initialPanel instanceof HTMLElement
        && desktopPointer.matches
        && window.innerWidth > 760
    ) {
        focusPanel(initialPanel);
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
