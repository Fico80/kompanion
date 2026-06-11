// Thin backend API wrapper. UI modules should not repeat fetch details.

const JSON_HEADERS = { "Content-Type": "application/json" };

async function requestJson(url, options = {}) {
    const response = await fetch(url, options);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
}

export function executeBackendCommand(command) {
    return requestJson("/api/execute", {
        method: "POST",
        headers: JSON_HEADERS,
        body: JSON.stringify({ command }),
    });
}

export function fetchSuggestions() {
    return requestJson("/api/memory/suggestions");
}

export function fetchLogs(limit = 200) {
    return requestJson(`/api/logs?limit=${limit}`);
}

export function fetchSettings() {
    return requestJson("/api/settings");
}

export function saveSettings(payload) {
    return requestJson("/api/settings", {
        method: "POST",
        headers: JSON_HEADERS,
        body: JSON.stringify(payload),
    });
}

export function deleteLog(id) {
    return fetch(`/api/logs/${id}`, { method: "DELETE" });
}

export function deleteAllLogs() {
    return fetch("/api/logs", { method: "DELETE" });
}
