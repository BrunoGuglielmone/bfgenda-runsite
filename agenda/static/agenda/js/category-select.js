(() => {
    "use strict";

    const NEUTRAL_COLOR = "#9A9EAD";
    const SELECTOR = "select[data-category-select-input]";

    const normalizeColor = (value) => {
        const color = String(value || "").trim();
        return /^#[0-9a-f]{6}$/i.test(color) ? color : NEUTRAL_COLOR;
    };

    const updateCategorySelect = (select) => {
        if (!(select instanceof HTMLSelectElement)) {
            return;
        }

        const shell = select.closest("[data-category-select]");
        if (!(shell instanceof HTMLElement)) {
            return;
        }

        const option = select.options[select.selectedIndex];
        const color = normalizeColor(option?.dataset.categoryColor);
        shell.style.setProperty("--category-select-color", color);
        shell.dataset.categorySelected = select.value ? "true" : "false";
    };

    const initializeCategorySelects = (root = document) => {
        if (root instanceof Element && root.matches(SELECTOR)) {
            updateCategorySelect(root);
        }
        root.querySelectorAll?.(SELECTOR).forEach(updateCategorySelect);
    };

    document.addEventListener("change", (event) => {
        if (event.target instanceof HTMLSelectElement && event.target.matches(SELECTOR)) {
            updateCategorySelect(event.target);
        }
    });

    const start = () => {
        initializeCategorySelects(document);
        if (!(document.body instanceof HTMLElement)) {
            return;
        }

        const observer = new MutationObserver((mutations) => {
            for (const mutation of mutations) {
                for (const node of mutation.addedNodes) {
                    if (node instanceof Element) {
                        initializeCategorySelects(node);
                    }
                }
            }
        });

        observer.observe(document.body, {childList: true, subtree: true});
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start, {once: true});
    } else {
        start();
    }
})();
