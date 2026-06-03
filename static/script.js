document.addEventListener("DOMContentLoaded", () => {
    const commandInput = document.getElementById("command-input");
    const submitBtn = document.getElementById("submit-btn");
    const resultAlert = document.getElementById("result-alert");
    const alertMessage = document.getElementById("alert-message");
    const historyList = document.getElementById("history-list");
    const quickTiles = document.querySelectorAll(".tile");

    // Load command history from localStorage
    let commandHistory = [];
    try {
        commandHistory = JSON.parse(localStorage.getItem("assistant_history")) || [];
    } catch (error) {
        console.warn("Ignoring invalid assistant history:", error);
        localStorage.removeItem("assistant_history");
    }
    let historyIndex = -1; // Current pointer for up/down arrows

    // Initialize history rendering
    renderHistory();

    // Event listener for Submit button
    submitBtn.addEventListener("click", () => {
        executeCommand(commandInput.value);
    });

    // Keyboard handlers (Enter to execute, Arrow Up/Down to navigate history)
    commandInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            executeCommand(commandInput.value);
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            navigateHistory("up");
        } else if (e.key === "ArrowDown") {
            e.preventDefault();
            navigateHistory("down");
        }
    });

    // Quick Start Tiles click events
    quickTiles.forEach(tile => {
        tile.addEventListener("click", () => {
            const command = tile.getAttribute("data-command");
            commandInput.value = command;
            commandInput.focus();
            executeCommand(command);
        });
    });

    // Load suggestions from backend
    loadSuggestions();

    async function loadSuggestions() {
        try {
            const res = await fetch("/api/memory/suggestions");
            if (!res.ok) return;
            const data = await res.json();
            renderSuggestions(data);
        } catch (e) {
            // Silently ignore if backend not reachable yet
        }
    }

    function renderSuggestions(suggestions) {
        const container = document.getElementById("suggestion-tiles");
        if (!suggestions || suggestions.length === 0) {
            container.innerHTML = `<div class="empty-history">Suggestions appear automatically after repeated commands.</div>`;
            return;
        }
        container.innerHTML = suggestions.map(s => {
            const label = s.app_name || s.command;
            const subtitle = `used ${s.count}x`;
            return `<button class="tile" data-command="${escapeHtml(s.command)}">
                <span class="tile-title">${escapeHtml(label)}</span>
                <span class="tile-subtitle">${escapeHtml(subtitle)}</span>
            </button>`;
        }).join("");

        container.querySelectorAll(".tile").forEach(tile => {
            tile.addEventListener("click", () => {
                const command = tile.getAttribute("data-command");
                commandInput.value = command;
                commandInput.focus();
                executeCommand(command);
            });
        });
    }

    // Execute Command API call
    async function executeCommand(commandText) {
        const cleanCommand = commandText.trim();
        if (!cleanCommand) return;

        // Visual loading state
        setLoading(true);

        try {
            const response = await fetch("/api/execute", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ command: cleanCommand })
            });

            if (!response.ok) {
                throw new Error(`HTTP error. Status: ${response.status}`);
            }

            const data = await response.json();
            const result = data.result;
            const stage = data.parsed?._stage ?? "?";
            const action = data.parsed?.action ?? "?";

            // Handle success / failure UI states
            if (result.success) {
                showAlert("success", result.message, stage, action);
                addToHistory(cleanCommand, "success", stage, action);
            } else {
                showAlert("error", result.message, stage, action);
                addToHistory(cleanCommand, "error", stage, action);
            }
            
            // Clear input on success
            if (result.success) {
                commandInput.value = "";
            }

        } catch (error) {
            console.error("Fetch error:", error);
            showAlert("error", `Connection error: ${error.message}. Is the Python backend running?`);
            addToHistory(cleanCommand, "error");
        } finally {
            setLoading(false);
            historyIndex = -1; // Reset history selector pointer
        }
    }

    // Toggle loading visual state
    function setLoading(isLoading) {
        if (isLoading) {
            commandInput.disabled = true;
            submitBtn.disabled = true;
            submitBtn.style.opacity = "0.5";
            commandInput.style.opacity = "0.7";
        } else {
            commandInput.disabled = false;
            submitBtn.disabled = false;
            submitBtn.style.opacity = "1";
            commandInput.style.opacity = "1";
            commandInput.focus();
        }
    }

    // Display Alert Overlay
    function showAlert(type, text, stage, action) {
        resultAlert.className = `result-alert ${type}`;
        const stageLabel = stage && action ? ` <span class="stage-badge">${stage} -> ${action}</span>` : "";
        alertMessage.innerHTML = escapeHtml(text) + stageLabel;
        
        // Simple fade-in effect
        resultAlert.style.display = "block";
        
        // Auto hide alert after 8 seconds (gives enough time to read)
        if (window.alertTimeout) {
            clearTimeout(window.alertTimeout);
        }
        window.alertTimeout = setTimeout(() => {
            resultAlert.style.display = "none";
        }, 8000);
    }

    // History log logic
    function addToHistory(command, status, stage, action) {
        commandHistory = commandHistory.filter(item => item.command !== command);
        commandHistory.unshift({ command, status, stage, action, time: new Date().toLocaleTimeString() });

        // Limit local history cache to 8 items
        if (commandHistory.length > 8) {
            commandHistory.pop();
        }

        // Save cache
        localStorage.setItem("assistant_history", JSON.stringify(commandHistory));
        renderHistory();
    }

    function renderHistory() {
        if (commandHistory.length === 0) {
            historyList.innerHTML = `<div class="empty-history">No commands yet. Type a command above or click a quick-start tile.</div>`;
            return;
        }

        historyList.innerHTML = commandHistory.map(item => `
            <div class="history-item">
                <span class="history-command" title="Click to copy">${escapeHtml(item.command)}</span>
                <span class="history-meta">
                    ${item.stage ? `<span class="stage-badge">${item.stage} -> ${item.action}</span>` : ""}
                    <span class="history-status-badge ${item.status}">${item.status === "success" ? "✓" : "✗"}</span>
                </span>
            </div>
        `).join("");

        // Make history items clickable to populate the input
        const historyItems = historyList.querySelectorAll(".history-item");
        historyItems.forEach((el, index) => {
            el.addEventListener("click", () => {
                commandInput.value = commandHistory[index].command;
                commandInput.focus();
            });
        });
    }

    // Navigate history via Arrow keys (up/down)
    function navigateHistory(direction) {
        if (commandHistory.length === 0) return;

        if (direction === "up") {
            if (historyIndex < commandHistory.length - 1) {
                historyIndex++;
                commandInput.value = commandHistory[historyIndex].command;
            }
        } else if (direction === "down") {
            if (historyIndex > 0) {
                historyIndex--;
                commandInput.value = commandHistory[historyIndex].command;
            } else if (historyIndex === 0) {
                historyIndex = -1;
                commandInput.value = "";
            }
        }
    }

    // Simple HTML escaping helper
    function escapeHtml(unsafe) {
        return unsafe
             .replace(/&/g, "&amp;")
             .replace(/</g, "&lt;")
             .replace(/>/g, "&gt;")
             .replace(/"/g, "&quot;")
             .replace(/'/g, "&#039;");
    }
});
