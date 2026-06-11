// Entry point — wires all modules together.

import { initTabs }                from "./tabs.js";
import { initCommands }            from "./commands.js";
import { initLogs, loadLogs }      from "./logs.js";
import { initRuntimeStatus }       from "./runtimeStatus.js";
import { initSettings, loadSettings } from "./settings.js";

document.addEventListener("DOMContentLoaded", () => {
    initCommands();
    initLogs();
    initSettings();
    initRuntimeStatus();
    initTabs((tab) => {
        if (tab === "logs")     loadLogs();
        if (tab === "settings") loadSettings();
    });
});
