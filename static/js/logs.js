// Logs tab: fetch from backend, render, filter, delete.

import { deleteAllLogs, deleteLog, fetchLogs } from "./api.js";
import { qs, qsa, on, setHtml } from "./lib/dom.js";
import { emptyState, logRow } from "./templates.js";

let allLogs      = [];
let activeFilter = "all";

export function initLogs() {
    _bindFilterButtons();
    _bindClearAll();
}

export async function loadLogs() {
    try {
        allLogs = await fetchLogs();
        _render();
    } catch (_) { /* backend not running */ }
}

// -- Rendering ------------------------------------------------------

function _render() {
    const list = qs("#logs-list");
    const rows = _filtered();

    if (rows.length === 0) {
        setHtml(list, emptyState("No logs found."));
        return;
    }

    setHtml(list, rows.map(logRow).join(""));
    qsa(".log-delete-btn", list).forEach(btn => {
        on(btn, "click", (e) => {
            e.stopPropagation();
            _deleteOne(Number(btn.dataset.id));
        });
    });
}

// -- Filter ---------------------------------------------------------

function _filtered() {
    if (activeFilter === "success") return allLogs.filter(l => l.success);
    if (activeFilter === "error")   return allLogs.filter(l => !l.success);
    return allLogs;
}

function _bindFilterButtons() {
    qsa(".logs-filter-btn").forEach(btn => {
        on(btn, "click", () => {
            qsa(".logs-filter-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            activeFilter = btn.dataset.filter;
            _render();
        });
    });
}

// -- Delete ---------------------------------------------------------

async function _deleteOne(id) {
    await deleteLog(id);
    allLogs = allLogs.filter(l => l.id !== id);
    _render();
}

function _bindClearAll() {
    on(qs("#clear-logs-btn"), "click", async () => {
        if (!confirm("Delete all logs?")) return;
        await deleteAllLogs();
        allLogs = [];
        _render();
    });
}
