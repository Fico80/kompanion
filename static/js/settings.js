// Settings tab: load from and save to backend .env via /api/settings.

import { fetchSettings, saveSettings } from "./api.js";
import { qs, qsa, on } from "./lib/dom.js";

export function initSettings() {
    on(qs("#settings-save-btn"), "click", _save);
}

export async function loadSettings() {
    try {
        const data = await fetchSettings();
        qsa("[data-key]", qs("#tab-settings")).forEach(el => {
            const val = data[el.dataset.key] ?? "";
            el.value = val;
        });
    } catch (_) { /* backend not running */ }
}

// ── Save ──────────────────────────────────────────────────────────

async function _save() {
    const payload = {};
    qsa("[data-key]", qs("#tab-settings")).forEach(el => {
        payload[el.dataset.key] = el.value.trim();
    });

    const status = qs("#settings-save-status");
    try {
        await saveSettings(payload);
        _showStatus(status, "Saved — restart to apply changes.", "success");
    } catch (err) {
        _showStatus(status, `Error: ${err.message}`, "error");
    }
}

function _showStatus(el, text, type) {
    el.textContent = text;
    el.className   = `settings-save-status settings-save-status--${type}`;
    el.classList.remove("hidden");
    setTimeout(() => el.classList.add("hidden"), 5000);
}
