// Command execution, keyboard history and suggestion tiles.

import { executeBackendCommand, fetchSuggestions } from "./api.js";
import { CHEAT_SHEET } from "./data/cheatSheet.js";
import { QUICK_COMMANDS } from "./data/quickCommands.js";
import { qs, qsa, on, setHtml } from "./lib/dom.js";
import { readJson, writeJson } from "./lib/storage.js";
import { showAlert, setLoading } from "./ui.js";
import { cheatCard, commandTile, emptyState, suggestionTile } from "./templates.js";

const MAX_HISTORY = 8;
const HISTORY_KEY = "assistant_history";

let commandHistory = [];
let historyIndex   = -1;

export function initCommands() {
    commandHistory = readJson(HISTORY_KEY, []);
    _renderStaticContent();
    _bindInput();
    _bindCommandTiles(document);
    loadSuggestions();
}

// ── Public ────────────────────────────────────────────────────────

export async function executeCommand(text) {
    const command = text.trim();
    if (!command) return;

    setLoading(true);
    try {
        const data   = await executeBackendCommand(command);
        const result = data.result;
        const stage  = data.parsed?._stage ?? "?";
        const action = data.parsed?.action  ?? "?";

        if (result.success) {
            showAlert("success", result.message, stage, action);
            _addToHistory(command, "success", stage, action);
            document.getElementById("command-input").value = "";
        } else {
            showAlert("error", result.message, stage, action);
            _addToHistory(command, "error", stage, action);
        }
    } catch (err) {
        showAlert("error", `Connection error: ${err.message}. Is the backend running?`);
        _addToHistory(command, "error");
    } finally {
        setLoading(false);
        historyIndex = -1;
    }
}

export async function loadSuggestions() {
    try {
        _renderSuggestions(await fetchSuggestions());
    } catch (_) { /* backend not ready yet */ }
}

// -- Static content -------------------------------------------------

function _renderStaticContent() {
    setHtml(qs("#quick-tiles"), QUICK_COMMANDS.map(commandTile).join(""));
    setHtml(qs("#cheat-sheet"), CHEAT_SHEET.map(cheatCard).join(""));
}

// -- Input binding --------------------------------------------------

function _bindInput() {
    const input     = qs("#command-input");
    const submitBtn = qs("#submit-btn");

    on(submitBtn, "click", () => executeCommand(input.value));

    on(input, "keydown", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            executeCommand(input.value);
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            _navigate("up");
        } else if (e.key === "ArrowDown") {
            e.preventDefault();
            _navigate("down");
        }
    });
}

function _bindCommandTiles(root) {
    qsa(".tile[data-command]", root).forEach(tile => {
        on(tile, "click", () => {
            const cmd = tile.getAttribute("data-command");
            qs("#command-input").value = cmd;
            executeCommand(cmd);
        });
    });
}

// -- Keyboard history ----------------------------------------------

function _addToHistory(command, status, stage, action) {
    commandHistory = commandHistory.filter(i => i.command !== command);
    commandHistory.unshift({ command, status, stage, action, time: new Date().toLocaleTimeString() });
    if (commandHistory.length > MAX_HISTORY) commandHistory.pop();
    writeJson(HISTORY_KEY, commandHistory);
}

function _navigate(direction) {
    if (commandHistory.length === 0) return;
    const input = qs("#command-input");

    if (direction === "up" && historyIndex < commandHistory.length - 1) {
        historyIndex++;
    } else if (direction === "down") {
        if (historyIndex > 0) historyIndex--;
        else if (historyIndex === 0) { historyIndex = -1; input.value = ""; return; }
    }
    if (historyIndex >= 0) input.value = commandHistory[historyIndex].command;
}

// -- Suggestions ----------------------------------------------------

function _renderSuggestions(suggestions) {
    const container = qs("#suggestion-tiles");
    if (!suggestions?.length) {
        setHtml(container, emptyState("Suggestions appear automatically after repeated commands."));
        return;
    }

    setHtml(container, suggestions.map(suggestionTile).join(""));
    _bindCommandTiles(container);
}
