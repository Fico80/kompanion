// Render-only helpers. Keep user-provided values escaped at the boundary.

import { escapeHtml } from "./lib/html.js";

export function emptyState(message) {
    return `<div class="empty-history">${escapeHtml(message)}</div>`;
}

export function commandTile({ title, subtitle, command }) {
    return `
        <button class="tile" data-command="${escapeHtml(command)}">
            <span class="tile-title">${escapeHtml(title)}</span>
            <span class="tile-subtitle">${escapeHtml(subtitle)}</span>
        </button>
    `;
}

export function suggestionTile(suggestion) {
    return commandTile({
        title: suggestion.app_name || suggestion.command,
        subtitle: `used ${suggestion.count}x`,
        command: suggestion.command,
    });
}

export function cheatCard({ title, body }) {
    return `
        <div class="cheat-card">
            <h3>${escapeHtml(title)}</h3>
            <p>${escapeHtml(body)}</p>
        </div>
    `;
}

export function stageBadge(stage, action) {
    if (!stage || !action) return "";
    return `<span class="stage-badge">${escapeHtml(stage)} &rarr; ${escapeHtml(action)}</span>`;
}

export function statusBadge(isSuccess) {
    const state = isSuccess ? "success" : "error";
    const label = isSuccess ? "&check;" : "&times;";
    return `<span class="history-status-badge ${state}">${label}</span>`;
}

export function logRow(log) {
    const time = (log.ts ?? "").replace("T", " ").slice(0, 19);

    return `
        <div class="log-item ${log.success ? "" : "log-error"}" data-id="${log.id}">
            <div class="log-main">
                <span class="log-text" title="${escapeHtml(log.raw_text ?? "")}">${escapeHtml(log.raw_text ?? "-")}</span>
                <div class="log-meta">
                    <span class="log-time">${escapeHtml(time)}</span>
                    ${stageBadge(log.stage, log.action)}
                </div>
            </div>
            <div class="log-controls">
                ${statusBadge(log.success)}
                <button class="log-delete-btn" data-id="${log.id}" title="Delete">&times;</button>
            </div>
        </div>
    `;
}
