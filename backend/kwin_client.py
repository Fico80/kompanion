import json
import subprocess
import shutil
import os
import time
import random
import string
import threading

def generate_random_id(length=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def run_dbus_cmd(args):
    """Executes a D-Bus CLI command and returns its standard output."""
    try:
        res = subprocess.run(args, capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"KWin Client D-Bus Error: {e.stderr.strip()}")
        return None

def load_and_run_kwin_script(js_code: str, plugin_name: str) -> bool:
    """Writes JS code to a temp file, loads it in KWin, runs it, and schedules cleanup."""
    temp_path = f"/tmp/{plugin_name}.js"
    with open(temp_path, "w") as f:
        f.write(js_code)
        
    try:
        # Load script (returns the integer ID, e.g. "0")
        load_args = [
            "qdbus-qt6", "org.kde.KWin", "/Scripting",
            "org.kde.kwin.Scripting.loadScript", temp_path, plugin_name
        ]
        script_id = run_dbus_cmd(load_args)
        if script_id is None:
            # Try unloading first in case it is already registered
            unload_args = [
                "qdbus-qt6", "org.kde.KWin", "/Scripting",
                "org.kde.kwin.Scripting.unloadScript", plugin_name
            ]
            run_dbus_cmd(unload_args)
            script_id = run_dbus_cmd(load_args)
            if script_id is None:
                return False
            
        # Run script
        run_args = [
            "qdbus-qt6", "org.kde.KWin", f"/Scripting/Script{script_id}",
            "org.kde.kwin.Script.run"
        ]
        run_dbus_cmd(run_args)
        
        # Schedule cleanup in a background thread to prevent blocking
        def cleanup():
            time.sleep(18)  # Wait 18 seconds to ensure new window spawn + timeout triggers
            unload_args = [
                "qdbus-qt6", "org.kde.KWin", "/Scripting",
                "org.kde.kwin.Scripting.unloadScript", plugin_name
            ]
            run_dbus_cmd(unload_args)
            try:
                os.remove(temp_path)
            except OSError:
                pass
                
        threading.Thread(target=cleanup, daemon=True).start()
        return True
    except Exception as e:
        print(f"Exception during load/run of KWin script: {e}")
        try:
            os.remove(temp_path)
        except OSError:
            pass
        return False

def _js_escape(s: str) -> str:
    """Escapes a string for safe embedding inside a JavaScript double-quoted string literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")

_LAST_WINDOW_STATE_PATH = "/tmp/lokaler_assistent_last_window_state.json"

def _read_last_window_state() -> dict | None:
    try:
        with open(_LAST_WINDOW_STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return None

def _move_with_kwin_script(window_class: str, desktop: int) -> bool:
    """Move all windows matching window_class to a virtual desktop via KWin scripting."""
    esc_class = _js_escape(window_class.lower())
    js = f"""
var clients = workspace.clientList();
var moved = 0;
for (var i = 0; i < clients.length; i++) {{
    var c = clients[i];
    if (c.resourceClass.toLowerCase() === "{esc_class}" ||
        c.resourceName.toLowerCase() === "{esc_class}") {{
        c.desktop = {desktop + 1};
        moved++;
    }}
}}
print("[kwin-move] " + moved + " window(s) with class={esc_class} -> desktop {desktop + 1}");
"""
    return load_and_run_kwin_script(js, f"kompanion_move_desktop_{generate_random_id()}")

def _list_windows_debug() -> list[dict]:
    """Returns all open windows via qdbus for debugging."""
    try:
        result = subprocess.run(
            ["qdbus-qt6", "org.kde.KWin", "/KWin", "org.kde.KWin.queryWindowInfo"],
            capture_output=True, text=True, timeout=3
        )
        lines = result.stdout.strip().splitlines()
        windows = []
        current = {}
        for line in lines:
            if ": " in line:
                k, _, v = line.partition(": ")
                current[k.strip()] = v.strip()
            elif not line.strip() and current:
                windows.append(current)
                current = {}
        if current:
            windows.append(current)
        return windows
    except Exception:
        return []

def restore_last_window_state() -> bool:
    state = _read_last_window_state()
    if not state:
        return False
    geom = state.get("geometry") or {}
    return apply_window_rules(
        window_class=state.get("window_class", "__active_window__"),
        window_title=state.get("window_title", ""),
        layout=None,
        desktop=state.get("desktop"),
        monitor=state.get("monitor"),
        new_window=False,
        restore_geometry=geom,
        save_previous=False,
    )

def apply_window_rules(window_class: str, window_title: str, layout: str = None, desktop: int = None, monitor: int = None, new_window: bool = True, from_desktop: int = None, restore_geometry: dict | None = None, save_previous: bool = True) -> bool:
    """
    Builds the JavaScript to position a window and runs it via KWin.
    
    - window_class: filter keyword for the window class name
    - window_title: filter keyword for the window title
    - layout: "left" | "right" | "full" | None
    - desktop: int (0-indexed desktop) or None
    - monitor: int (0-indexed monitor) or None
    """
    plugin_name = f"assistant_layout_{generate_random_id()}"


    # Map Python None values to Javascript equivalents
    js_desktop = desktop if desktop is not None else -1
    js_monitor = monitor if monitor is not None else -1
    js_layout = layout if layout is not None else ""
    js_restore_geometry = json.dumps(restore_geometry or {})
    js_save_previous = "true" if save_previous and not new_window and restore_geometry is None else "false"

    safe_class = _js_escape(window_class)
    safe_title = _js_escape(window_title)
    safe_layout = _js_escape(js_layout)
    js_new_window = "true" if new_window else "false"
    js_from_desktop = from_desktop if from_desktop is not None else -1

    # Construct JavaScript code
    js_template = f"""// KWin Script generated by Local Assistant
const targetClass = "{safe_class}";
const targetTitle = "{safe_title}";
const targetActiveWindow = targetClass === "__active_window__";
const desktopIndex = {js_desktop};
const monitorIndex = {js_monitor};
const layout = "{safe_layout}";
const restoreGeometry = {js_restore_geometry};
const savePreviousState = {js_save_previous};
const statePath = "{_LAST_WINDOW_STATE_PATH}";

function sortedScreensLeftToRight() {{
    const screens = workspace.screens || [];
    const withAreas = [];
    for (let i = 0; i < screens.length; i++) {{
        const area = screens[i].geometry;
        withAreas.push({{ screen: screens[i], x: area.x, index: i }});
    }}
    withAreas.sort(function(a, b) {{
        if (a.x === b.x) {{
            return a.index - b.index;
        }}
        return a.x - b.x;
    }});
    return withAreas.map(function(item) {{ return item.screen; }});
}}

function targetOutputFor(w) {{
    if (monitorIndex === -1) {{
        return w.output;
    }}
    const screens = sortedScreensLeftToRight();
    if (screens[monitorIndex]) {{
        return screens[monitorIndex];
    }}
    return w.output;
}}

function matchWindow(w, isSpawned) {{
    if (targetActiveWindow) {{
        return true;
    }}
    const wClass = (w.resourceClass || "").toLowerCase();
    const wName = (w.resourceName || "").toLowerCase();
    const wTitle = (w.caption || "").toLowerCase();
    
    const tClass = targetClass.toLowerCase();
    const tTitle = targetTitle.toLowerCase();
    
    // On spawn, if we have a class target, match immediately by class
    // (helps when the window caption is still empty or is just 'Loading...')
    if (isSpawned && tClass) {{
        if (wClass.indexOf(tClass) !== -1 || wName.indexOf(tClass) !== -1) {{
            return true;
        }}
    }}
    
    // Normal match (existing windows): require class and title matching if title is specified
    if (tClass && (wClass.indexOf(tClass) !== -1 || wName.indexOf(tClass) !== -1)) {{
        if (!tTitle || wTitle.indexOf(tTitle) !== -1) {{
            return true;
        }}
    }}
    if (tTitle && wTitle.indexOf(tTitle) !== -1) {{
        return true;
    }}
    return false;
}}

function screenIndexFor(w) {{
    const screens = sortedScreensLeftToRight();
    for (let i = 0; i < screens.length; i++) {{
        if (screens[i] === w.output) {{
            return i;
        }}
    }}
    return -1;
}}

function desktopIndexFor(w) {{
    if (!w.desktops || !w.desktops.length) {{
        return -1;
    }}
    const desktops = workspace.desktops || [];
    for (let i = 0; i < desktops.length; i++) {{
        if (desktops[i] === w.desktops[0]) {{
            return i;
        }}
    }}
    return -1;
}}

function savePrevious(w) {{
    if (!savePreviousState) {{
        return;
    }}
    try {{
        const g = w.frameGeometry;
        const state = {{
            window_class: (w.resourceClass || w.resourceName || "").toLowerCase(),
            window_title: "",
            desktop: desktopIndexFor(w),
            monitor: screenIndexFor(w),
            geometry: {{ x: g.x, y: g.y, width: g.width, height: g.height }}
        }};
        const file = new QFile(statePath);
        if (file.open(QIODevice.WriteOnly | QIODevice.Truncate)) {{
            file.write(JSON.stringify(state));
            file.close();
        }}
    }} catch (e) {{}}
}}

function applyLayout(w) {{
    savePrevious(w);

    // 1. Move to virtual desktop (desktops array contains VirtualDesktop objects)
    let targetDesktop = workspace.currentDesktop;
    if (desktopIndex !== -1 && workspace.desktops[desktopIndex]) {{
        targetDesktop = workspace.desktops[desktopIndex];
        w.desktops = [targetDesktop];
    }}
    
    // 2. Move to monitor screen (screens array contains Output objects)
    let targetScreen = targetOutputFor(w);
    if (monitorIndex !== -1 && targetScreen) {{
        workspace.sendClientToScreen(w, targetScreen);
    }}
    
    // 3. Restore explicit geometry or set tiling layout / geometry
    if (restoreGeometry && restoreGeometry.width && restoreGeometry.height) {{
        if (w.setMaximize) {{
            w.setMaximize(false, false);
        }}
        w.frameGeometry = {{
            x: restoreGeometry.x,
            y: restoreGeometry.y,
            width: restoreGeometry.width,
            height: restoreGeometry.height
        }};
        return;
    }}

    if (layout && targetScreen) {{
        // Query the clientArea for the target screen directly to avoid coordinate race conditions
        const area = workspace.clientArea(KWin.MaximizeArea, targetScreen, targetDesktop);
        
        let newX = area.x;
        let newY = area.y;
        let newWidth = area.width;
        let newHeight = area.height;
        
        if (layout === "left") {{
            newWidth = area.width / 2;
        }} else if (layout === "right") {{
            newX = area.x + area.width / 2;
            newWidth = area.width / 2;
        }}
        
        if (w.setMaximize) {{
            w.setMaximize(false, false);
        }}
        w.frameGeometry = {{
            x: newX,
            y: newY,
            width: newWidth,
            height: newHeight
        }};
    }}
}}

function applyLayoutRepeated(w) {{
    applyLayout(w);
    const delays = [300, 800, 1400];
    for (let i = 0; i < delays.length; i++) {{
        const timer = new QTimer();
        timer.interval = delays[i];
        timer.singleShot = true;
        timer.timeout.connect(function() {{ applyLayout(w); }});
        timer.start();
    }}
}}

function applyLayoutWithRetry(w) {{
    applyLayout(w);
    const timer = new QTimer();
    timer.interval = 600;
    timer.singleShot = true;
    timer.timeout.connect(function() {{ applyLayout(w); }});
    timer.start();
}}

function currentActiveWindow() {{
    if (workspace.activeWindow) {{
        return workspace.activeWindow;
    }}
    if (workspace.activeClient) {{
        return workspace.activeClient;
    }}
    return null;
}}

const newWindow = {js_new_window};
const fromDesktop = {js_from_desktop};

// New windows: repeated correction (app resizes after open).
// Existing windows: apply + one retry after 600ms in case the first assignment was ignored.
const applyFn = newWindow ? applyLayoutRepeated : applyLayoutWithRetry;

let found = false;
if (!newWindow) {{
    if (targetActiveWindow) {{
        const active = currentActiveWindow();
        if (active) {{
            applyFn(active);
            found = true;
        }}
    }}

    // 1. Try the active (focused) window first. Fastest, no desktop switch needed.
    if (!found && fromDesktop === -1) {{
        const active = currentActiveWindow();
        if (active && matchWindow(active, false)) {{
            applyFn(active);
            found = true;
        }}
    }}

    // 2. Scan by temporarily switching to each virtual desktop.
    //    workspace.stackingOrder only returns windows on the CURRENT desktop in KWin 6,
    //    so we iterate all desktops. The JS engine is synchronous, and the compositor batches
    //    visual updates, so there is no visible flicker during the scan.
    if (!found) {{
        const originalDesktop = workspace.currentDesktop;
        const desktops = workspace.desktops;

        for (let d = 0; d < desktops.length && !found; d++) {{
            if (fromDesktop !== -1 && d !== fromDesktop) continue;
            workspace.currentDesktop = desktops[d];
            const wins = workspace.stackingOrder;
            for (let i = 0; i < wins.length && !found; i++) {{
                if (matchWindow(wins[i], false)) {{
                    applyFn(wins[i]);
                    found = true;
                }}
            }}
        }}

        workspace.currentDesktop = originalDesktop;
    }}
}}

// Only wait for a new window when we actually launched one.
if (!found && newWindow) {{
    const onWindowAdded = function(w) {{
        if (matchWindow(w, true)) {{
            applyFn(w);
            workspace.windowAdded.disconnect(onWindowAdded);
        }}
    }};
    workspace.windowAdded.connect(onWindowAdded);

    const timeoutTimer = new QTimer();
    timeoutTimer.interval = 15000;
    timeoutTimer.singleShot = true;
    timeoutTimer.timeout.connect(function() {{
        workspace.windowAdded.disconnect(onWindowAdded);
    }});
    timeoutTimer.start();
}}
"""
    return load_and_run_kwin_script(js_template, plugin_name)
