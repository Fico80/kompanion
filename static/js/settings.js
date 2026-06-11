// Settings tab: load from and save to backend .env via /api/settings.

import { fetchSettings, saveSettings } from "./api.js";
import { qs, qsa, on } from "./lib/dom.js";

export function initSettings() {
    on(qs("#settings-save-btn"), "click", _save);
    on(qs("#hotkey-record-btn"), "click", _recordHotkey);
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

function _recordHotkey() {
    const input = qs("#hotkey-input");
    const button = qs("#hotkey-record-btn");
    if (!input || !button) return;

    const previous = button.textContent;
    button.textContent = "Press a key...";
    button.classList.add("is-recording");
    input.focus();

    const capture = (event) => {
        event.preventDefault();
        event.stopPropagation();

        const keyName = _keyboardEventToEvdev(event);
        if (keyName) input.value = keyName;

        button.textContent = previous;
        button.classList.remove("is-recording");
        window.removeEventListener("keydown", capture, true);
    };

    window.addEventListener("keydown", capture, true);
}

function _keyboardEventToEvdev(event) {
    const directMap = {
        AltLeft: "KEY_LEFTALT",
        AltRight: "KEY_RIGHTALT",
        Backspace: "KEY_BACKSPACE",
        CapsLock: "KEY_CAPSLOCK",
        ControlLeft: "KEY_LEFTCTRL",
        ControlRight: "KEY_RIGHTCTRL",
        Delete: "KEY_DELETE",
        End: "KEY_END",
        Enter: "KEY_ENTER",
        Escape: "KEY_ESC",
        Home: "KEY_HOME",
        Insert: "KEY_INSERT",
        MetaLeft: "KEY_LEFTMETA",
        MetaRight: "KEY_RIGHTMETA",
        PageDown: "KEY_PAGEDOWN",
        PageUp: "KEY_PAGEUP",
        ShiftLeft: "KEY_LEFTSHIFT",
        ShiftRight: "KEY_RIGHTSHIFT",
        Space: "KEY_SPACE",
        Tab: "KEY_TAB",
    };

    if (directMap[event.code]) return directMap[event.code];
    if (/^Key[A-Z]$/.test(event.code)) return `KEY_${event.code.slice(3)}`;
    if (/^Digit[0-9]$/.test(event.code)) return `KEY_${event.code.slice(5)}`;
    if (/^F(?:[1-9]|1[0-2])$/.test(event.code)) return `KEY_${event.code}`;
    return "";
}
