// Tab switching. Each tab name maps to its content element id.

import { qs, qsa, on } from "./lib/dom.js";

const TAB_CONTENT = {
    commands: "tab-commands",
    logs:     "tab-logs",
    settings: "tab-settings",
};

export function initTabs(onSwitch) {
    qsa(".tab-btn").forEach(btn => {
        on(btn, "click", () => _activate(btn.dataset.tab, onSwitch));
    });
}

function _activate(tab, onSwitch) {
    qsa(".tab-btn").forEach(b =>
        b.classList.toggle("active", b.dataset.tab === tab)
    );
    Object.entries(TAB_CONTENT).forEach(([name, id]) =>
        qs(`#${id}`).classList.toggle("hidden", name !== tab)
    );
    onSwitch?.(tab);
}
