"use strict";

(() => {
    const STORAGE_KEY = "bfgenda-theme-preference";
    const VALID_PREFERENCES = new Set(["sistema", "claro", "oscuro"]);
    const root = document.documentElement;
    const systemDark = window.matchMedia("(prefers-color-scheme: dark)");
    let activePreference = "sistema";

    function normalizePreference(value) {
        return VALID_PREFERENCES.has(value) ? value : "sistema";
    }

    function storedPreference() {
        try {
            return window.localStorage.getItem(STORAGE_KEY);
        } catch (error) {
            return null;
        }
    }

    function persistPreference(value) {
        try {
            window.localStorage.setItem(STORAGE_KEY, value);
        } catch (error) {
            // El tema sigue funcionando aunque el navegador bloquee storage.
        }
    }

    function resolvedTheme(preference) {
        if (preference === "oscuro") {
            return "dark";
        }

        if (preference === "claro") {
            return "light";
        }

        return systemDark.matches ? "dark" : "light";
    }

    function updateBrowserColor(theme) {
        const themeColor = document.querySelector('meta[name="theme-color"]');
        const colorScheme = document.querySelector('meta[name="color-scheme"]');

        if (themeColor instanceof HTMLMetaElement) {
            themeColor.content = theme === "dark" ? "#05060E" : "#E7DFF7";
        }

        if (colorScheme instanceof HTMLMetaElement) {
            colorScheme.content = theme === "dark" ? "dark" : "light";
        }
    }

    function applyPreference(value, {persist = false} = {}) {
        activePreference = normalizePreference(value);
        const theme = resolvedTheme(activePreference);

        root.dataset.themePreference = activePreference;
        root.dataset.theme = theme;
        root.style.colorScheme = theme;
        updateBrowserColor(theme);

        if (persist) {
            persistPreference(activePreference);
        }

        document.dispatchEvent(new CustomEvent("bfgenda:theme-changed", {
            detail: {preference: activePreference, theme},
        }));
    }

    const authenticated = root.dataset.themeAuthenticated === "true";
    const serverPreference = normalizePreference(root.dataset.themePreference);
    const initialPreference = authenticated
        ? serverPreference
        : normalizePreference(storedPreference() || serverPreference);

    window.BFGendaTheme = {
        applyPreference,
        getPreference: () => activePreference,
        getTheme: () => root.dataset.theme,
    };

    applyPreference(initialPreference, {persist: authenticated});

    const handleSystemChange = () => {
        if (activePreference === "sistema") {
            applyPreference(activePreference);
        }
    };

    if (typeof systemDark.addEventListener === "function") {
        systemDark.addEventListener("change", handleSystemChange);
    } else if (typeof systemDark.addListener === "function") {
        systemDark.addListener(handleSystemChange);
    }
})();
