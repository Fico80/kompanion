// Shared UI state helpers used across modules.

import { qs } from "./lib/dom.js";
import { escapeHtml } from "./lib/html.js";
import { stageBadge } from "./templates.js";

export { escapeHtml };

export function showAlert(type, text, stage, action) {
    const resultAlert  = qs("#result-alert");
    const alertMessage = qs("#alert-message");

    resultAlert.className = `result-alert ${type}`;
    alertMessage.innerHTML = escapeHtml(text) + stageBadge(stage, action);
    resultAlert.style.display = "block";

    if (window._alertTimeout) clearTimeout(window._alertTimeout);
    window._alertTimeout = setTimeout(() => {
        resultAlert.style.display = "none";
    }, 8000);
}

export function setLoading(isLoading) {
    const commandInput = qs("#command-input");
    const submitBtn    = qs("#submit-btn");

    commandInput.disabled  = isLoading;
    submitBtn.disabled     = isLoading;
    submitBtn.style.opacity  = isLoading ? "0.5" : "1";
    commandInput.style.opacity = isLoading ? "0.7" : "1";
    if (!isLoading) commandInput.focus();
}
