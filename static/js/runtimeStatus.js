// Footer runtime status derived from configured local/cloud endpoints.

import { fetchSettings } from "./api.js";
import { qs } from "./lib/dom.js";

const ENDPOINT_KEYS = ["LLM_BASE_URL", "STT_BASE_URL", "VISION_BASE_URL"];

export async function initRuntimeStatus() {
    try {
        renderRuntimeStatus(classifyRuntime(await fetchSettings()));
    } catch (_) {
        renderRuntimeStatus({ mode: "local", label: "Local runtime" });
    }
}

function classifyRuntime(settings) {
    const endpoints = ENDPOINT_KEYS
        .map(key => settings[key])
        .filter(Boolean);

    const hasCloud = endpoints.some(isCloudEndpoint);
    const hasLocal = endpoints.length === 0 || endpoints.some(isLocalEndpoint);

    if (hasCloud && hasLocal) return { mode: "hybrid", label: "Hybrid runtime" };
    if (hasCloud) return { mode: "cloud", label: "Cloud runtime" };
    return { mode: "local", label: "Local runtime" };
}

function isLocalEndpoint(value) {
    return /(^|\/\/)(localhost|127\.0\.0\.1|0\.0\.0\.0)(:|\/|$)/i.test(value);
}

function isCloudEndpoint(value) {
    return /^https?:\/\//i.test(value) && !isLocalEndpoint(value);
}

function renderRuntimeStatus({ mode, label }) {
    const indicator = qs("#runtime-status");
    const labelEl = qs("#runtime-status-label");
    const dot = qs("#runtime-status-dot");

    indicator?.setAttribute("data-runtime", mode);
    if (labelEl) labelEl.textContent = label;
    dot?.setAttribute("title", label);
}
