#!/usr/bin/env python3
import os
import sys
import re
import subprocess
import tempfile
import math
import time
import threading
import requests
import evdev
from evdev import InputDevice, categorize, ecodes

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QPointF, QRectF, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QRadialGradient, QGuiApplication, QFont, QPainterPath
from PyQt6.QtWidgets import QApplication, QWidget, QGraphicsOpacityEffect

ASSISTANT_URL = "http://127.0.0.1:8000/api/execute"
HOTKEY = ecodes.KEY_RIGHTCTRL
HUD_STYLE = "kompanion"    # overridden by HUD_STYLE env var in main()
HUD_POSITION = "bottom-right"  # overridden by HUD_POSITION env var in main()

def load_env():
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not os.path.exists(env_path):
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

def find_keyboards():
    devices = []
    for path in evdev.list_devices():
        try:
            dev = InputDevice(path)
            caps = dev.capabilities()
            if ecodes.EV_KEY in caps and HOTKEY in caps[ecodes.EV_KEY]:
                devices.append(dev)
        except Exception:
            pass
    return devices

def transcribe(audio_path):
    whisper_url = os.environ.get("WHISPER_BASE_URL", "").rstrip("/")
    stt_key = os.environ.get("STT_API_KEY", "")
    language = os.environ.get("WHISPER_LANGUAGE", "en")

    if whisper_url:
        is_local = "127.0.0.1" in whisper_url or "localhost" in whisper_url
        if is_local:
            url = whisper_url + "/inference"
            headers = {}
            model = "whisper-1"
        else:
            url = whisper_url + "/v1/audio/transcriptions"
            headers = {"Authorization": f"Bearer {stt_key}"} if stt_key else {}
            model = os.environ.get("STT_MODEL", "whisper-large-v3-turbo")
        timeout = 60 if is_local else 15
    else:
        stt_base = os.environ.get("STT_BASE_URL", "").rstrip("/")
        url = (stt_base + "/audio/transcriptions") if stt_base else ""
        if not url:
            return ""
        headers = {"Authorization": f"Bearer {stt_key}"} if stt_key else {}
        model = os.environ.get("STT_MODEL", "whisper-large-v3-turbo")
        timeout = 15

    with open(audio_path, "rb") as f:
        resp = requests.post(
            url,
            headers=headers,
            files={"file": ("recording.wav", f, "audio/wav")},
            data={"model": model, "language": language, "response_format": "json"},
            timeout=timeout,
        )
    resp.raise_for_status()
    return resp.json().get("text", "").strip()

def execute_command(text):
    resp = requests.post(ASSISTANT_URL, json={"command": text}, timeout=10)
    resp.raise_for_status()
    return resp.json()

# Actions that should be spoken aloud (query responses, not "open Firefox" etc.)
_SPEAK_ACTIONS = {"query_calendar", "query_weather", "query_system", "query_spotify", "save_note", "append_note", "clipboard_task", "query_shortcut_suggestions", "save_shortcut_sequence", "search_files", "select_item", "needs_clarification", "undo", "close_all_windows", "confirm", "add_task", "query_tasks", "complete_task", "query_notes", "voice_recall"}

_ASSISTANT_NAME = r"(?:jarvis|comp|komp|companion|kompanion)"
_SLEEP_COMMAND_RE = re.compile(
    r"\b(?:"
    r"(?:jarvis|comp|komp|companion|kompanion)\s+(?:aus|stopp?|stoppen|ruhe|schlaf(?:en)?|deaktivieren?|stop|sleep|quit)|"
    r"(?:geh|gehe)\s+schlafen|"
    r"(?:go\s+to\s+sleep|go\s+to\s+rest)|"
    r"schlaf\s+(?:weiter|ein)|"
    r"h[öo]r\s+auf\s+(?:zu\s+)?(?:h[öo]ren|zuzuh[öo]ren)|"
    r"stop\s+listening|stop\s+hearing|"
    r"nicht\s+mehr\s+(?:h[öo]ren|zuh[öo]ren)|"
    r"zur[üu]ck\s+(?:in\s+den\s+)?wake[-\s]?word[-\s]?modus|"
    r"back\s+to\s+wake[-\s]?word|"
    r"das\s+war'?s|that'?s\s+(?:all|it)|"
    r"goodbye|good\s+bye|"
    r"bye\s+(?:jarvis|comp|komp|companion|kompanion)|"
    r"danke(?:\s+(?:jarvis|comp|komp|companion|kompanion))?|"
    r"thanks(?:\s+(?:jarvis|comp|komp|companion|kompanion))?"
    r")\b",
    re.IGNORECASE,
)

_WAIT_COMMAND_RE = re.compile(
    r"\b(?:"
    r"warte\s+(?:kurz|mal|einen\s+moment)|"
    r"wait\s+(?:a\s+moment|a\s+sec(?:ond)?|please)|"
    r"bleib\s+(?:wach|dran|aktiv)|"
    r"stay\s+(?:active|awake|on)|"
    r"h[öo]r\s+(?:weiter\s+)?zu|"
    r"keep\s+listening|"
    r"ich\s+[üu]berlege\s+(?:kurz|noch)|"
    r"let\s+me\s+think|"
    r"hold\s+on|"
    r"moment(?:\s+bitte)?|"
    r"one\s+second|just\s+a\s+sec|"
    r"eine\s+sekunde"
    r")\b",
    re.IGNORECASE,
)

_REPEAT_COMMAND_RE = re.compile(
    r"\b(?:"
    r"nochmal|"
    r"noch\s+mal|"
    r"wiederhol(?:e|en)?(?:\s+(?:das|den\s+befehl))?|"
    r"mach\s+(?:das\s+)?noch(?:\s+ein)?mal|"
    r"gleich\s+nochmal|"
    r"do\s+(?:that\s+)?again|"
    r"repeat(?:\s+(?:that|the\s+command))?|"
    r"once\s+more|"
    r"again"
    r")\b",
    re.IGNORECASE,
)

_RECALL_COMMAND_RE = re.compile(
    r"\b(?:"
    r"was\s+(?:habe|hab|hatte)\s+ich\s+gesagt|"
    r"was\s+hast\s+du\s+verstanden|"
    r"wiederhol(?:e)?\s+was\s+ich\s+gesagt\s+habe|"
    r"sag\s+mir\s+was\s+du\s+verstanden\s+hast|"
    r"what\s+did\s+i\s+(?:say|ask)|"
    r"what\s+did\s+you\s+(?:understand|hear)|"
    r"repeat\s+what\s+i\s+said"
    r")\b",
    re.IGNORECASE,
)

def is_sleep_command(text: str) -> bool:
    """Return True for local voice commands that should end the active session."""
    return bool(_SLEEP_COMMAND_RE.search(text.strip()))

def is_wait_command(text: str) -> bool:
    """Return True for local voice commands that should keep the session open."""
    return bool(_WAIT_COMMAND_RE.search(text.strip()))

def is_repeat_command(text: str) -> bool:
    """Return True for local voice commands that should repeat a safe action."""
    return bool(_REPEAT_COMMAND_RE.search(text.strip()))

def is_recall_command(text: str) -> bool:
    """Return True for local voice commands that ask for the last transcript."""
    return bool(_RECALL_COMMAND_RE.search(text.strip()))

_CONTEXT_PRONOUN_RE = re.compile(
    r"\b(?:es|das|dies(?:e|es)?|ihn|sie|das\s+fenster|die\s+app|die\s+anwendung)\b",
    re.IGNORECASE,
)

def _contextual_window_command(text: str, context: dict | None):
    """Return (handled, command_or_message) for pronoun-based window commands."""
    text_l = text.lower().strip()
    has_pronoun = bool(_CONTEXT_PRONOUN_RE.search(text_l))
    if not has_pronoun:
        return False, ""

    if not context:
        if re.search(r"\b(links|rechts|vollbild|maximier|größer|schlie[sß]|mach|schieb|verschieb|monitor|bildschirm|arbeitsfläche|desktop|workspace|fläche)\b", text_l):
            return True, "I do not know which window you mean yet."
        return False, ""

    app_ref = context.get("app_ref") or context.get("app_name")
    if not app_ref:
        return True, "I do not know which window you mean yet."

    if re.search(r"\b(schlie[sß]e?|beende?|mach)\b", text_l) and re.search(r"\b(zu|schlie[sß]|beende?|weg)\b", text_l):
        return True, f"schließe {app_ref}"

    if re.search(r"\b(zur[üu]ck|retour|wieder\s+zur[üu]ck)\b", text_l) and re.search(r"\b(verschieb|schieb|schiebe|beweg|bring|setz|mach)\b", text_l):
        return True, context.get("move_back_command") or "verschiebe aktives fenster zurück"

    placement = []
    monitor_match = re.search(r"\b(?:auf|an|zum|zu|in|auf\s+den|auf\s+dem)?\s*(?:den|dem|der)?\s*(linke[nm]?|linker|linkem|linken|rechte[nm]?|rechter|rechtem|rechten)\s+(?:monitor|bildschirm|screen)\b", text_l)
    if monitor_match:
        placement.append("auf linkem Monitor" if monitor_match.group(1).startswith("link") else "auf rechtem Monitor")

    desktop_match = re.search(r"\b(?:auf|an|zu|zur|in)?\s*(?:die|der)?\s*(?:arbeitsfläche|desktop|workspace|fläche)\s*(\d+)\b", text_l)
    if desktop_match:
        placement.append(f"auf Arbeitsfläche {desktop_match.group(1)}")

    placement_without_monitor = re.sub(
        r"\b(?:auf|an|zum|zu|in|auf\s+den|auf\s+dem)?\s*(?:den|dem|der)?\s*(linke[nm]?|linker|linkem|linken|rechte[nm]?|rechter|rechtem|rechten)\s+(?:monitor|bildschirm|screen)\b",
        "",
        text_l,
    )
    if re.search(r"\b(?:nach\s+)?(links|linke\s+seite)\b", placement_without_monitor):
        placement.append("links")
    elif re.search(r"\b(?:nach\s+)?(rechts|rechte\s+seite)\b", placement_without_monitor):
        placement.append("rechts")
    elif re.search(r"\b(vollbild|maximier(?:e|en)?|größer|groesser|full(?:screen)?)\b", text_l):
        placement.append("vollbild")

    if placement and re.search(r"\b(mach|verschieb|schieb|schiebe|beweg|bring|setz|pack|tu|auf)\b", text_l):
        return True, f"verschiebe aktives fenster {' '.join(placement)}"

    return False, ""

def _clean_for_tts(text: str, response_lang: str = "en") -> str:
    """Convert structured result text into natural speech."""
    # 1. Unit conversions before emoji strip. Degree symbols live in the symbol range.
    if response_lang == "de":
        text = re.sub(r"(\d+(?:[.,]\d+)?)\s*°C", r"\1 Grad", text)
        text = re.sub(r"(\d+(?:[.,]\d+)?)\s*°", r"\1 Grad", text)
        text = re.sub(r"(\d+)\s*%", r"\1 Prozent", text)
    else:
        text = re.sub(r"(\d+(?:[.,]\d+)?)\s*°C", r"\1 degrees Celsius", text)
        text = re.sub(r"(\d+(?:[.,]\d+)?)\s*°", r"\1 degrees", text)
        text = re.sub(r"(\d+)\s*%", r"\1 percent", text)
    if response_lang == "de":
        text = re.sub(r"(\d+)\s*km/h", r"\1 Kilometer pro Stunde", text)
    else:
        text = re.sub(r"(\d+)\s*km/h", r"\1 kilometers per hour", text)
    text = re.sub(r"@\s*(\d+)\s*MHz", r"\1 Megahertz", text)
    text = re.sub(r"(\d+(?:[.,]\d+)?)\s*GB", r"\1 Gigabyte", text)

    # 2. Separators. Must run before emoji strip removes dashes and slashes.
    text = re.sub(r"\s*·\s*", ", ", text)
    text = re.sub(r"\s*—\s*", ", ", text)
    text = re.sub(r"\s*/\s*", ", ", text)

    # 3. Time format: "10:00" -> natural speech per language.
    def _time(m):
        h, mins = m.group(1), m.group(2)
        if response_lang == "de":
            return f"um {h} Uhr" if mins == "00" else f"um {h} Uhr {mins}"
        return f"at {h}" if mins == "00" else f"at {h} {mins}"
    text = re.sub(r"\b(\d{1,2}):(\d{2})\b", _time, text)

    # 4. Remove emojis and decoration. Keep letters, digits and punctuation.
    text = re.sub(r"[^\w\s.,!?:;äöüÄÖÜß\-\n]", " ", text)

    # 5. Abbreviations
    text = re.sub(r"\bMin\b", "Minimum", text)
    text = re.sub(r"\bMax\b", "Maximum", text)

    # 6. Newlines -> sentence breaks. Header colon plus dot -> single dot.
    text = re.sub(r"\n+", ". ", text)
    text = re.sub(r":\.", ".", text)

    # 7. Clean up spacing and punctuation
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r",\s*,", ",", text)
    text = re.sub(r"\.{2,}", ".", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

_piper_cache: dict = {}

def _load_piper_voice(model_path: str):
    if model_path not in _piper_cache:
        from piper.voice import PiperVoice
        _piper_cache[model_path] = PiperVoice.load(model_path)
    return _piper_cache[model_path]

def speak(text: str, response_lang: str = "en"):
    """Speak text via Piper (local neural TTS). Falls back to espeak-ng."""
    lang = "de" if response_lang == "de" else "en"
    clean = _clean_for_tts(text, response_lang)
    if not clean:
        return

    # Piper: local neural TTS
    piper_model = os.path.expanduser(
        os.environ.get(f"PIPER_MODEL_{lang.upper()}") or os.environ.get("PIPER_MODEL", "")
    )
    if piper_model and os.path.exists(piper_model):
        try:
            import wave
            voice = _load_piper_voice(piper_model)
            fd, tmp = tempfile.mkstemp(suffix=".wav", prefix="tts_")
            os.close(fd)
            wav_file = wave.open(tmp, "wb")
            voice.synthesize_wav(clean, wav_file)
            wav_file.close()
            subprocess.run(["paplay", tmp], timeout=60)
            os.remove(tmp)
            return
        except Exception:
            pass

    # espeak-ng: local fallback
    try:
        subprocess.run(["espeak-ng", "-v", lang, "-s", "145", clean], timeout=30)
    except Exception:
        pass

def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "ja", "on"}

class MediaPauseManager:
    def __init__(self):
        self._paused_players = set()
        self._lock = threading.Lock()

    def pause_for_voice(self):
        """Pause active MPRIS players and remember only players we paused."""
        if not _env_bool("VOICE_PAUSE_MEDIA_ON_TRIGGER", True):
            return
        try:
            players = subprocess.run(
                ["playerctl", "-l"],
                capture_output=True,
                text=True,
                timeout=0.5,
            )
        except Exception:
            return
        if players.returncode != 0:
            return

        for player in players.stdout.splitlines():
            player = player.strip()
            if not player:
                continue
            try:
                status = subprocess.run(
                    ["playerctl", "-p", player, "status"],
                    capture_output=True,
                    text=True,
                    timeout=0.5,
                )
                if status.returncode != 0 or status.stdout.strip().lower() != "playing":
                    continue
                subprocess.run(
                    ["playerctl", "-p", player, "pause"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=0.5,
                )
                with self._lock:
                    self._paused_players.add(player)
            except Exception:
                continue

    def resume_after_voice(self):
        if not _env_bool("VOICE_RESUME_MEDIA_ON_SLEEP", True):
            self.clear()
            return
        with self._lock:
            players = list(self._paused_players)
            self._paused_players.clear()
        for player in players:
            try:
                status = subprocess.run(
                    ["playerctl", "-p", player, "status"],
                    capture_output=True,
                    text=True,
                    timeout=0.5,
                )
                if status.returncode == 0 and status.stdout.strip().lower() == "paused":
                    subprocess.run(
                        ["playerctl", "-p", player, "play"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=0.5,
                    )
            except Exception:
                continue

    def clear(self):
        with self._lock:
            self._paused_players.clear()

_MEDIA_PAUSE_MANAGER = MediaPauseManager()

def pause_media_for_voice():
    _MEDIA_PAUSE_MANAGER.pause_for_voice()

def resume_media_after_voice():
    _MEDIA_PAUSE_MANAGER.resume_after_voice()

def forget_paused_media():
    _MEDIA_PAUSE_MANAGER.clear()


# --- Voice Orb Widget: pulsating rings + central glowing dot ---

class VoiceOrbWidget(QWidget):
    _STATE_CFG = {
        "listening":  {"interval": 0.88, "duration": 1.7, "max_r": 32 if HUD_STYLE == "pill" else 54, "color": QColor(74, 220, 198)},
        "processing": {"interval": 0.46, "duration": 1.0, "max_r": 32 if HUD_STYLE == "pill" else 54, "color": QColor(91, 167, 245)},
        "success":    {"interval": 999,  "duration": 1.4, "max_r": 32 if HUD_STYLE == "pill" else 54, "color": QColor(79, 190, 135)},
        "error":      {"interval": 999,  "duration": 1.4, "max_r": 32 if HUD_STYLE == "pill" else 54, "color": QColor(232, 109, 105)},
        "session":    {"interval": 2.8,  "duration": 3.0, "max_r": 22 if HUD_STYLE == "pill" else 38, "color": QColor(118, 203, 176)},
    }
    _ORB_COLORS = {
        "listening":  QColor(98, 226, 205, 235),
        "processing": QColor(98, 169, 245, 235),
        "success":    QColor(82, 196, 142, 240),
        "error":      QColor(232, 109, 105, 240),
        "session":    QColor(118, 203, 176, 185),
    }
    _STATE_LABEL = {
        "listening":  "Listening",
        "processing": "Thinking",
        "success":    "Done",
        "error":      "Oops",
        "session":    "Ready",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = "listening"
        self.text = ""
        self.rings = []
        self.last_spawn = 0.0
        self.start_time = time.time()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def set_state(self, state, text=""):
        self.state = state
        self.text = text
        if state in ("success", "error"):
            now = time.time()
            self.rings = [now, now - 0.18, now - 0.36]

    def _body_text(self) -> str:
        if not self.text:
            return ""
        body = self.text.splitlines()[-1] if "\n" in self.text else self.text
        body = body.strip()
        label = self._STATE_LABEL.get(self.state, "").strip().lower()
        normalized = body.lower().strip(".! ")
        if label and normalized == label:
            return ""
        if self.state == "processing" and normalized in {"processing", "thinking", "understanding audio"}:
            return ""
        return body

    def _tick(self):
        now = time.time()
        cfg = self._STATE_CFG.get(self.state, self._STATE_CFG["listening"])
        if now - self.last_spawn > cfg["interval"]:
            self.rings.append(now)
            self.last_spawn = now
        self.rings = [r for r in self.rings if now - r < cfg["duration"]]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if HUD_STYLE == "pill":
            self._paint_pill(painter)
        elif HUD_STYLE == "kompanion":
            self._paint_kompanion(painter)
        else:
            self._paint_mini(painter)

    def _draw_orb(self, painter, cx, cy, orb_r):
        """Draw pulsing rings and orb core at the given center."""
        now = time.time()
        cfg = self._STATE_CFG.get(self.state, self._STATE_CFG["listening"])
        ring_col = cfg["color"]

        for birth in self.rings:
            age = now - birth
            progress = min(age / cfg["duration"], 1.0)
            eased = 1.0 - (1.0 - progress) ** 2
            radius = orb_r + (cfg["max_r"] - orb_r) * eased
            alpha = int(170 * (1.0 - progress) ** 1.4)
            stroke = max(0.5, 2.0 * (1.0 - progress))
            c = QColor(ring_col)
            c.setAlpha(alpha)
            painter.setPen(QPen(c, stroke))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), radius, radius)

        outer = QColor(ring_col)
        outer.setAlpha(28)
        painter.setPen(QPen(outer, 1.2))
        painter.drawEllipse(QPointF(cx, cy), orb_r + 5, orb_r + 5)

        # Deep shadow background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(4, 4, 10, 255)))
        painter.drawEllipse(QPointF(cx, cy), orb_r + 1, orb_r + 1)

        # 3D sphere: radial gradient, light source top-left
        orb_col = self._ORB_COLORS.get(self.state, self._ORB_COLORS["listening"])
        r, g, b = orb_col.red(), orb_col.green(), orb_col.blue()
        fl_x = cx - orb_r * 0.3
        fl_y = cy - orb_r * 0.3
        sphere_grad = QRadialGradient(cx, cy, orb_r, fl_x, fl_y)
        sphere_grad.setColorAt(0.0,  QColor(min(255, r + 95), min(255, g + 95), min(255, b + 95), 255))
        sphere_grad.setColorAt(0.45, QColor(r, g, b, 245))
        sphere_grad.setColorAt(1.0,  QColor(max(0, r - 75), max(0, g - 75), max(0, b - 75), 255))
        painter.setBrush(QBrush(sphere_grad))
        painter.drawEllipse(QPointF(cx, cy), orb_r, orb_r)

        # Specular highlight (white glint, top-left)
        spec_r = orb_r * 0.42
        spec_grad = QRadialGradient(fl_x, fl_y, spec_r)
        spec_grad.setColorAt(0.0, QColor(255, 255, 255, 155))
        spec_grad.setColorAt(0.55, QColor(255, 255, 255, 30))
        spec_grad.setColorAt(1.0,  QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(spec_grad))
        painter.drawEllipse(QPointF(cx, cy), orb_r, orb_r)

        if self.state == "processing":
            elapsed = time.time() - self.start_time
            angle = (elapsed * 280) % 360
            arc_pen = QPen(QColor(255, 255, 255, 170), 2.0)
            arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(arc_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            inner_r = orb_r - 3
            rect = QRectF(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2)
            painter.drawArc(rect, int(angle * 16), 100 * 16)

    def _paint_energy_orb_unused(self, painter, cx, cy, orb_r):
        now = time.time()
        orb_col = self._ORB_COLORS.get(self.state, self._ORB_COLORS["listening"])
        r, g, b = orb_col.red(), orb_col.green(), orb_col.blue()
        speed_mul = {"listening": 0.8, "processing": 2.2, "success": 0.5, "error": 0.3}.get(self.state, 0.8)

        painter.setPen(Qt.PenStyle.NoPen)

        # Outer aura glow (3 soft gradient layers)
        for scale, alpha in ((1.9, 9), (1.5, 22), (1.2, 42)):
            ag = QRadialGradient(cx, cy, orb_r * scale)
            ag.setColorAt(0.0, QColor(r, g, b, alpha))
            ag.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setBrush(QBrush(ag))
            painter.drawEllipse(QPointF(cx, cy), orb_r * scale, orb_r * scale)

        # Animated orbital rings: radius_factor, tilt_ratio, base_speed.
        orbitals = [
            (1.48, 0.18,  0.55),
            (1.38, 0.42, -0.38),
            (1.55, 0.12,  0.22),
            (1.32, 0.60, -0.50),
        ]
        for rad_f, tilt, base_speed in orbitals:
            ring_a = orb_r * rad_f
            ring_b = ring_a * tilt
            angle  = math.degrees(now * base_speed * speed_mul)
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(angle)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(r, g, b, 35), 3.5))
            painter.drawEllipse(QPointF(0, 0), ring_a, ring_b)
            painter.setPen(QPen(QColor(min(255, r+40), min(255, g+40), min(255, b+40), 165), 1.0))
            painter.drawEllipse(QPointF(0, 0), ring_a, ring_b)
            painter.restore()

        # 3D core sphere
        fl_x = cx - orb_r * 0.3
        fl_y = cy - orb_r * 0.3
        sphere_grad = QRadialGradient(cx, cy, orb_r, fl_x, fl_y)
        sphere_grad.setColorAt(0.0,  QColor(min(255, r+110), min(255, g+110), min(255, b+110), 255))
        sphere_grad.setColorAt(0.4,  QColor(r, g, b, 248))
        sphere_grad.setColorAt(1.0,  QColor(max(0, r-70),  max(0, g-70),  max(0, b-70),  255))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(sphere_grad))
        painter.drawEllipse(QPointF(cx, cy), orb_r, orb_r)

        # Specular highlight
        spec_grad = QRadialGradient(fl_x, fl_y, orb_r * 0.42)
        spec_grad.setColorAt(0.0,  QColor(255, 255, 255, 180))
        spec_grad.setColorAt(0.55, QColor(255, 255, 255, 30))
        spec_grad.setColorAt(1.0,  QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(spec_grad))
        painter.drawEllipse(QPointF(cx, cy), orb_r, orb_r)

        # Inner bloom (bright core glow)
        bloom = QRadialGradient(cx, cy, orb_r * 0.38)
        bloom.setColorAt(0.0,  QColor(255, 255, 255, 210))
        bloom.setColorAt(0.4,  QColor(min(255, r+80), min(255, g+80), min(255, b+80), 90))
        bloom.setColorAt(1.0,  QColor(r, g, b, 0))
        painter.setBrush(QBrush(bloom))
        painter.drawEllipse(QPointF(cx, cy), orb_r * 0.38, orb_r * 0.38)

        # Processing arc on top
        if self.state == "processing":
            elapsed = time.time() - self.start_time
            angle = (elapsed * 280) % 360
            arc_pen = QPen(QColor(255, 255, 255, 170), 2.0)
            arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(arc_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            inner_r = orb_r - 3
            rect = QRectF(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2)
            painter.drawArc(rect, int(angle * 16), 100 * 16)

    def _paint_pill(self, painter):
        w, h = self.width(), self.height()
        cy = h / 2.0
        cx = 36.0
        orb_r = 20

        cfg = self._STATE_CFG.get(self.state, self._STATE_CFG["listening"])
        ring_col = cfg["color"]

        # Dark pill background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(12, 12, 22, 225)))
        painter.drawRoundedRect(QRectF(0, 0, w, h), 36, 36)

        # State-colored border
        border_col = QColor(ring_col)
        border_col.setAlpha(55)
        painter.setPen(QPen(border_col, 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(0.6, 0.6, w - 1.2, h - 1.2), 35.4, 35.4)

        # Vertical separator between orb and text
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1.0))
        painter.drawLine(72, 10, 72, h - 10)

        # Orb (rings + core)
        self._draw_orb(painter, cx, cy, orb_r)

        # Text area (right side)
        text_x = 82.0
        text_w = w - text_x - 12.0
        state_label = self._STATE_LABEL.get(self.state, "")
        font = QFont("Inter, Segoe UI, sans-serif", 9)
        font.setWeight(QFont.Weight.Medium)
        painter.setFont(font)
        label_col = QColor(ring_col)
        label_col.setAlpha(200)
        painter.setPen(QPen(label_col, 1))

        body = self._body_text()
        if body:
            # State label upper half, body text lower half
            painter.drawText(
                QRectF(text_x, cy - 20, text_w, 20),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                state_label,
            )
            body_font = QFont("Inter, Segoe UI, sans-serif", 9)
            painter.setFont(body_font)
            painter.setPen(QPen(QColor(210, 210, 210, 185), 1))
            fm = painter.fontMetrics()
            elided = fm.elidedText(body, Qt.TextElideMode.ElideRight, int(text_w))
            painter.drawText(
                QRectF(text_x, cy + 2, text_w, 18),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                elided,
            )
        else:
            # No body text: center state label vertically
            painter.drawText(
                QRectF(text_x, 0, text_w, h),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                state_label,
            )

    def _paint_mini(self, painter):
        w, h = self.width(), self.height()
        cx = w / 2.0
        cy = h / 2.0 - 18

        now      = time.time()
        orb_col  = self._ORB_COLORS.get(self.state, self._ORB_COLORS["listening"])
        r, g, b  = orb_col.red(), orb_col.green(), orb_col.blue()
        cfg      = self._STATE_CFG.get(self.state, self._STATE_CFG["listening"])
        ring_col = cfg["color"]
        speed    = {"listening": 0.72, "processing": 1.95, "success": 0.42, "error": 1.35}.get(self.state, 0.72)
        pulse    = 0.5 + 0.5 * math.sin(now * speed * 2.2)
        R        = min(w, h - 30) * 0.34
        wave_amp = 4.2 + pulse * 2.0

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setPen(Qt.PenStyle.NoPen)

        # The Sketchfab piece is a paid/no-AI 3D model, so the HUD renders a
        # procedural look-alike: luminous spherical strings, nodes and bloom.
        for scale, alpha in ((1.65, 12), (1.28, 26), (1.04, 44)):
            glow = QRadialGradient(cx, cy, R * scale)
            glow.setColorAt(0.0, QColor(min(255, r + 50), min(255, g + 50), min(255, b + 50), alpha))
            glow.setColorAt(0.52, QColor(r, g, b, alpha))
            glow.setColorAt(1.0, QColor(r, g, b, 0))
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(QPointF(cx, cy), R * scale, R * scale)

        core = QRadialGradient(cx, cy, R * 0.95, cx - R * 0.35, cy - R * 0.45)
        core.setColorAt(0.00, QColor(245, 255, 255, 92))
        core.setColorAt(0.20, QColor(min(255, r + 80), min(255, g + 80), min(255, b + 80), 72))
        core.setColorAt(0.58, QColor(r, g, b, 24))
        core.setColorAt(1.00, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(core))
        painter.drawEllipse(QPointF(cx, cy), R * 0.92, R * 0.92)

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)

        def project(phi, lam, radius=R, phase=0.0):
            spin = now * speed * 0.82 + phase
            lam2 = lam + spin
            wobble = wave_amp * math.sin(4.0 * lam + 3.0 * phi - now * speed * 2.7 + phase)
            rr = radius + wobble
            x3 = rr * math.cos(phi) * math.cos(lam2)
            y3 = rr * math.sin(phi)
            z3 = rr * math.cos(phi) * math.sin(lam2)
            tilt = -0.44
            y2 = y3 * math.cos(tilt) - z3 * math.sin(tilt)
            z2 = y3 * math.sin(tilt) + z3 * math.cos(tilt)
            perspective = 1.0 / (1.0 + z2 / (R * 3.1))
            return cx + x3 * perspective, cy - y2 * perspective, z2

        samples = 92
        for k, phi in enumerate((-1.05, -0.78, -0.52, -0.27, 0.0, 0.27, 0.52, 0.78, 1.05)):
            path = QPainterPath()
            avg_depth = 0.0
            for j in range(samples + 1):
                lam = 2.0 * math.pi * j / samples
                sx, sy, depth = project(phi, lam, phase=k * 0.22)
                avg_depth += depth
                if j == 0:
                    path.moveTo(sx, sy)
                else:
                    path.lineTo(sx, sy)
            depth_t = max(0.0, min(1.0, 0.5 + avg_depth / (samples * R * 1.8)))
            painter.strokePath(path, QPen(QColor(r, g, b, int(58 + 125 * depth_t)), 1.0))

        for k, lam in enumerate([i * math.pi / 7 for i in range(14)]):
            path = QPainterPath()
            front = 0.0
            for i in range(samples + 1):
                phi = -math.pi / 2 + math.pi * i / samples
                sx, sy, depth = project(phi, lam, phase=-k * 0.16)
                front += depth
                if i == 0:
                    path.moveTo(sx, sy)
                else:
                    path.lineTo(sx, sy)
            depth_t = max(0.0, min(1.0, 0.5 + front / (samples * R * 1.8)))
            painter.strokePath(path, QPen(QColor(min(255, r + 38), min(255, g + 38), min(255, b + 38), int(42 + 112 * depth_t)), 0.82))

        for idx, (tilt, squeeze, phase, width) in enumerate((
            (-28, 0.22, 0.0, 1.8),
            (18, 0.36, 1.7, 1.2),
            (64, 0.18, 3.1, 1.0),
            (-68, 0.48, 4.4, 0.9),
        )):
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(tilt + math.degrees(now * speed * (0.13 + idx * 0.04)))
            path = QPainterPath()
            orbit_r = R * (1.02 + idx * 0.045)
            for j in range(samples + 1):
                a = 2.0 * math.pi * j / samples
                ripple = math.sin(a * 5.0 - now * speed * 3.0 + phase) * 2.2
                x = (orbit_r + ripple) * math.cos(a)
                y = (orbit_r * squeeze + ripple * 0.35) * math.sin(a)
                if j == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            painter.strokePath(path, QPen(QColor(min(255, r + 70), min(255, g + 70), min(255, b + 70), 120), width))
            painter.restore()

        painter.setPen(Qt.PenStyle.NoPen)
        for idx in range(54):
            phi = -1.25 + (idx % 9) * (2.5 / 8.0)
            lam = (idx * 2.399963 + now * speed * (0.32 + (idx % 5) * 0.035)) % (2.0 * math.pi)
            sx, sy, depth = project(phi, lam, radius=R * (0.93 + (idx % 4) * 0.025), phase=idx * 0.13)
            if depth < -R * 0.72:
                continue
            t = max(0.0, min(1.0, 0.54 + depth / (R * 1.65)))
            spark_r = 0.8 + 1.25 * t + (0.35 * pulse if idx % 7 == 0 else 0.0)
            painter.setBrush(QBrush(QColor(min(255, r + 82), min(255, g + 82), min(255, b + 82), int(70 + 175 * t))))
            painter.drawEllipse(QPointF(sx, sy), spark_r, spark_r)

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        glass = QRadialGradient(cx, cy, R * 0.52, cx - R * 0.22, cy - R * 0.30)
        glass.setColorAt(0.0, QColor(255, 255, 255, 70))
        glass.setColorAt(0.42, QColor(255, 255, 255, 8))
        glass.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(glass))
        painter.drawEllipse(QPointF(cx, cy), R * 0.72, R * 0.72)

        # State label
        state_label = self._STATE_LABEL.get(self.state, "")
        font = QFont("Inter, Segoe UI, sans-serif", 9)
        painter.setFont(font)
        lc = QColor(ring_col)
        lc.setAlpha(190)
        painter.setPen(QPen(lc, 1))
        text_y = cy + R + wave_amp + 8
        painter.drawText(
            QRectF(4, text_y, w - 8, 16),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            state_label,
        )
        body = self._body_text()
        if body:
            body_font = QFont("Inter, Segoe UI, sans-serif", 8)
            painter.setFont(body_font)
            painter.setPen(QPen(QColor(188, 202, 200, 150), 1))
            fm = painter.fontMetrics()
            elided = fm.elidedText(body, Qt.TextElideMode.ElideRight, w - 18)
            painter.drawText(
                QRectF(9, text_y + 16, w - 18, 15),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                elided,
            )

    def _paint_kompanion(self, painter):
        w, h = self.width(), self.height()
        now = time.time()
        cfg = self._STATE_CFG.get(self.state, self._STATE_CFG["listening"])
        state_col = QColor(cfg["color"])
        orb_col = self._ORB_COLORS.get(self.state, self._ORB_COLORS["listening"])
        r, g, b = orb_col.red(), orb_col.green(), orb_col.blue()
        pulse_speed = {
            "listening": 1.7,
            "processing": 3.4,
            "success": 1.1,
            "error": 1.2,
            "session": 0.8,
        }.get(self.state, 1.3)
        pulse = 0.5 + 0.5 * math.sin(now * pulse_speed)

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setPen(Qt.PenStyle.NoPen)

        # Soft compact panel.
        panel = QRectF(8, 8, w - 16, h - 16)
        painter.setBrush(QBrush(QColor(11, 14, 20, 216)))
        painter.drawRoundedRect(panel, 18, 18)

        border = QColor(state_col)
        border.setAlpha(60 + int(28 * pulse))
        painter.setPen(QPen(border, 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(panel.adjusted(0.8, 0.8, -0.8, -0.8), 17, 17)

        cx = w / 2.0
        face_w = 56.0
        face_h = 48.0
        face = QRectF(cx - face_w / 2.0, 22, face_w, face_h)

        for birth in self.rings:
            age = now - birth
            progress = min(age / cfg["duration"], 1.0)
            eased = 1.0 - (1.0 - progress) ** 2
            glow_r = 30 + 24 * eased
            c = QColor(state_col)
            c.setAlpha(int(72 * (1.0 - progress) ** 1.35))
            painter.setPen(QPen(c, max(0.7, 1.8 * (1.0 - progress))))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(cx, face.center().y()), glow_r, glow_r * 0.82)

        painter.setPen(Qt.PenStyle.NoPen)
        glow = QRadialGradient(cx, face.center().y(), 56)
        glow.setColorAt(0.0, QColor(r, g, b, 52))
        glow.setColorAt(0.62, QColor(r, g, b, 16))
        glow.setColorAt(1.0, QColor(r, g, b, 0))
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(QPointF(cx, face.center().y()), 50, 42)

        face_grad = QRadialGradient(face.center().x(), face.center().y(), 42, face.left() + 17, face.top() + 12)
        face_grad.setColorAt(0.0, QColor(min(255, r + 78), min(255, g + 78), min(255, b + 78), 245))
        face_grad.setColorAt(0.48, QColor(r, g, b, 235))
        face_grad.setColorAt(1.0, QColor(max(0, r - 48), max(0, g - 48), max(0, b - 48), 235))
        painter.setBrush(QBrush(face_grad))
        painter.drawRoundedRect(face, 16, 16)

        painter.setPen(QPen(QColor(255, 255, 255, 70), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(face.adjusted(0.8, 0.8, -0.8, -0.8), 15, 15)

        # K-shaped antenna: a tiny character mark rather than a logo badge.
        antenna_alpha = 175 + int(60 * pulse)
        antenna_pen = QPen(QColor(226, 255, 247, antenna_alpha), 2.2)
        antenna_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        antenna_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(antenna_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        stem_x = cx - 2.0
        stem_top = face.top() - 14.0
        stem_mid = face.top() + 2.0
        sway = math.sin(now * pulse_speed * 0.85) * (1.2 if self.state == "processing" else 0.55)
        painter.drawLine(QPointF(stem_x, stem_mid), QPointF(stem_x + sway, stem_top))
        painter.drawLine(QPointF(stem_x + 0.2, stem_mid - 1.0), QPointF(stem_x + 11.0 + sway, stem_top - 2.5))
        painter.drawLine(QPointF(stem_x + 0.2, stem_mid + 0.2), QPointF(stem_x + 10.5 - sway * 0.4, face.top() + 8.0))

        node_col = QColor(r, g, b, 92 + int(46 * pulse))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(node_col))
        painter.drawEllipse(QPointF(stem_x + 11.0 + sway, stem_top - 2.5), 2.8, 2.8)

        # Face details.
        eye_y = face.top() + 20
        left_eye_x = face.left() + 19
        right_eye_x = face.right() - 19
        eye_col = QColor(7, 17, 21, 210)
        if self.state == "processing":
            eye_w = 6.4
            eye_h = 3.0
        else:
            eye_w = 5.0
            eye_h = 6.0
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(eye_col))
        painter.drawEllipse(QPointF(left_eye_x, eye_y), eye_w, eye_h)
        painter.drawEllipse(QPointF(right_eye_x, eye_y), eye_w, eye_h)

        cheek = QColor(255, 255, 255, 44 if self.state != "error" else 30)
        painter.setBrush(QBrush(cheek))
        painter.drawEllipse(QPointF(face.left() + 13, face.top() + 31), 4.8, 2.1)
        painter.drawEllipse(QPointF(face.right() - 13, face.top() + 31), 4.8, 2.1)

        mouth_pen = QPen(QColor(8, 20, 24, 190), 1.8)
        mouth_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(mouth_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        mouth = QRectF(cx - 9, face.top() + 28, 18, 9)
        if self.state == "error":
            painter.drawArc(mouth, 25 * 16, 130 * 16)
        elif self.state == "processing":
            painter.drawLine(QPointF(cx - 6, face.top() + 33), QPointF(cx + 6, face.top() + 33))
        else:
            painter.drawArc(mouth, 200 * 16, 140 * 16)

        if self.state == "processing":
            dot_col = QColor(238, 255, 252, 180)
            painter.setPen(Qt.PenStyle.NoPen)
            for idx in range(3):
                a = now * 3.6 + idx * (2.0 * math.pi / 3.0)
                painter.setBrush(QBrush(dot_col))
                painter.drawEllipse(QPointF(cx + math.cos(a) * 40, face.center().y() + math.sin(a) * 30), 2.2, 2.2)

        label = self._STATE_LABEL.get(self.state, "")
        label_font = QFont("Inter, Segoe UI, sans-serif", 10)
        label_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(label_font)
        label_col = QColor(236, 244, 242, 230)
        painter.setPen(QPen(label_col, 1))
        painter.drawText(QRectF(10, 78, w - 20, 19), Qt.AlignmentFlag.AlignHCenter, label)

        body = self._body_text()
        if body:
            body_font = QFont("Inter, Segoe UI, sans-serif", 8)
            painter.setFont(body_font)
            painter.setPen(QPen(QColor(188, 202, 200, 165), 1))
            fm = painter.fontMetrics()
            elided = fm.elidedText(body, Qt.TextElideMode.ElideRight, w - 26)
            painter.drawText(QRectF(13, 98, w - 26, 18), Qt.AlignmentFlag.AlignHCenter, elided)


# --- Overlay Window (Orb HUD, bottom-right) ---

class OverlayWindow(QWidget):
    _MARGIN = 30

    def __init__(self):
        super().__init__()
        if HUD_STYLE == "pill":
            self._WIN_W, self._WIN_H = 380, 72
        elif HUD_STYLE == "kompanion":
            self._WIN_W, self._WIN_H = 156, 128
        else:
            self._WIN_W, self._WIN_H = 140, 126
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedSize(self._WIN_W, self._WIN_H)

        self.orb = VoiceOrbWidget(self)
        self.orb.setGeometry(0, 0, self._WIN_W, self._WIN_H)

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)

        self.fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_anim.setDuration(300)
        self.fade_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.fade_anim.finished.connect(self._on_fade_done)

        self.close_timer = QTimer(self)
        self.close_timer.setSingleShot(True)
        self.close_timer.timeout.connect(self.hide_overlay)

        # Wayland: reapply position after compositor maps the window
        self._pos_timer = QTimer(self)
        self._pos_timer.setSingleShot(True)
        self._pos_timer.timeout.connect(self._reapply_pos)

    def _get_pos(self):
        screen = QGuiApplication.primaryScreen().geometry()
        sw, sh = screen.width(), screen.height()
        m = self._MARGIN
        p = HUD_POSITION
        cx = (sw - self._WIN_W) // 2
        cy = (sh - self._WIN_H) // 2
        positions = {
            "bottom-right":  (sw - self._WIN_W - m, sh - self._WIN_H - m),
            "bottom-left":   (m,                    sh - self._WIN_H - m),
            "top-right":     (sw - self._WIN_W - m, m),
            "top-left":      (m,                    m),
            "bottom-center": (cx,                   sh - self._WIN_H - m),
            "top-center":    (cx,                   m),
            "center":        (cx,                   cy),
            "center-left":   (m,                    cy),
            "center-right":  (sw - self._WIN_W - m, cy),
        }
        return positions.get(p, positions["bottom-right"])

    def _reapply_pos(self):
        x, y = self._get_pos()
        self.move(x, y)

    def show_overlay(self, state="listening", text=""):
        self.close_timer.stop()
        self.orb.set_state(state, text)
        x, y = self._get_pos()
        self.setGeometry(x, y, self._WIN_W, self._WIN_H)
        self.fade_anim.stop()
        self.show()
        self.fade_anim.setStartValue(self.opacity_effect.opacity())
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.start()
        self._pos_timer.start(180)

    def update_state(self, state, text=""):
        self.orb.set_state(state, text)

    def show_result(self, success, text, duration=6500):
        self.update_state("success" if success else "error", text)
        self.close_timer.start(duration)

    def hide_overlay(self):
        self.fade_anim.stop()
        self.fade_anim.setStartValue(self.opacity_effect.opacity())
        self.fade_anim.setEndValue(0.0)
        self.fade_anim.start()

    def _on_fade_done(self):
        if self.opacity_effect.opacity() < 0.01:
            self.hide()


# --- Background Evdev Keyboard Thread ---

class KeyboardListenerThread(QThread):
    key_pressed = pyqtSignal()

    def __init__(self, keyboards):
        super().__init__()
        self.keyboards = keyboards
        self.running = True

    def run(self):
        import selectors
        
        sel = selectors.DefaultSelector()
        for dev in self.keyboards:
            sel.register(dev, selectors.EVENT_READ)
            
        while self.running:
            events = sel.select(timeout=0.1)
            for key, _ in events:
                dev = key.fileobj
                try:
                    for event in dev.read():
                        if event.type == ecodes.EV_KEY:
                            kev = categorize(event)
                            if kev.scancode == HOTKEY and kev.keystate == kev.key_up:
                                self.key_pressed.emit()
                except OSError:
                    pass

    def stop(self):
        self.running = False


# --- Wake-Word Thread (continuous listening via openWakeWord + webrtcvad) ---

class WakeWordThread(QThread):
    wakeword_detected = pyqtSignal()   # Show HUD "Listening..."
    audio_ready       = pyqtSignal(str)  # path to recorded WAV, ready for Whisper
    session_expired   = pyqtSignal()   # Session timed out, back to wake-word mode.
    error_occurred    = pyqtSignal(str)

    DEVICE_RATE    = 48000  # native mic rate — avoids PipeWire resampling artifacts
    RATE           = 16000  # OWW model input rate
    CHANNELS       = 1
    BLOCK_MS       = 80
    BLOCK_SAMPLES  = int(DEVICE_RATE * BLOCK_MS / 1000)   # 3840 samples per block at 48kHz
    # webrtcvad requires 10/20/30 ms sub-frames; 48kHz is supported
    VAD_FRAME_MS   = 30
    VAD_FRAME_SAMPLES = int(DEVICE_RATE * VAD_FRAME_MS / 1000)  # 1440 samples per frame
    WW_THRESHOLD   = 0.60
    WAKE_REARM_SECONDS = 1.5  # short guard after ending a session
    FAILED_WAKE_REARM_SECONDS = 2.0  # longer guard after false wake with no speech
    WAKE_CONSECUTIVE_BLOCKS = 2  # 2 x 80 ms above threshold before wake fires
    WAKE_VAD_GRACE_BLOCKS = 6  # accept wake scores only near detected speech
    SILENCE_BLOCKS   = 25   # 25 x 80 ms = 2.0 s silence, ends the utterance.
    NO_SPEECH_BLOCKS = 25   # 25 x 80 ms = 2.0 s silence after wake-word, gives up.
    MIN_SPEECH_BLOCKS = 4   # 4 x 80 ms = 320 ms min speech
    ONSET_BLOCKS   = 2      # 2 consecutive speech blocks to start session recording
    PRE_ROLL_BLOCKS = 6     # 6 x 80 ms = 480 ms pre-roll before trigger
    SESSION_TIMEOUT = 5.0  # seconds after last command execution
    LOCAL_WAIT_SECONDS = 30.0
    MAX_BLOCKS     = int(1000 / BLOCK_MS * int(os.environ.get("MAX_RECORD_SECONDS", "300")))  # silence-driven; this is just a safety cap

    def __init__(self, wake_word: str = "hey_jarvis_v0.1"):
        super().__init__()
        self.wake_word = wake_word
        self.running   = True
        self._busy     = False          # True while AudioWorker is processing
        self._session_until = 0.0       # timestamp until session mode is active
        self._wake_disabled_until = 0.0
        self.session_timeout = self._read_float_env("WAKE_SESSION_TIMEOUT", self.SESSION_TIMEOUT)
        _silence_secs = self._read_float_env("WAKE_SILENCE_SECONDS", self.SILENCE_BLOCKS * 0.08)
        self.silence_blocks = max(5, int(_silence_secs / 0.08))
        self.no_speech_blocks = self.silence_blocks
        self.local_wait_seconds = self._read_float_env("WAKE_LOCAL_WAIT_SECONDS", self.LOCAL_WAIT_SECONDS)
        self.ww_threshold = self._read_float_env("WAKE_WORD_THRESHOLD", self.WW_THRESHOLD)
        self.failed_wake_rearm_seconds = self._read_float_env(
            "WAKE_FAILED_REARM_SECONDS", self.FAILED_WAKE_REARM_SECONDS
        )
        self.wake_consecutive_blocks = max(
            1,
            int(self._read_float_env("WAKE_CONSECUTIVE_BLOCKS", self.WAKE_CONSECUTIVE_BLOCKS)),
        )
        self.wake_require_vad = self._read_bool_env("WAKE_REQUIRE_VAD", True)
        self.wake_vad_grace_blocks = max(
            0,
            int(self._read_float_env("WAKE_VAD_GRACE_BLOCKS", self.WAKE_VAD_GRACE_BLOCKS)),
        )
        self.wake_debug = self._read_bool_env("WAKE_DEBUG", False)

    @staticmethod
    def _read_float_env(name: str, default: float) -> float:
        try:
            return float(os.environ.get(name, default))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _read_bool_env(name: str, default: bool) -> bool:
        raw = os.environ.get(name)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "ja", "on"}

    # Called from the main thread after a command completes
    def extend_session(self, seconds: float | None = None):
        self._session_until = time.time() + (self.session_timeout if seconds is None else seconds)

    def end_session(self, rearm_seconds: float | None = None):
        self._session_until = 0.0
        self._busy = False
        self._wake_disabled_until = time.time() + (
            self.WAKE_REARM_SECONDS if rearm_seconds is None else rearm_seconds
        )

    def set_busy(self, busy: bool):
        self._busy = busy
        if not busy:
            pass  # session extension is handled by caller

    def _in_session(self) -> bool:
        return time.time() < self._session_until

    def stop(self):
        self.running = False

    @staticmethod
    def _play_ding():
        bell = "/usr/share/sounds/freedesktop/stereo/bell.oga"
        if os.path.exists(bell):
            subprocess.Popen(["paplay", bell],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def run(self):
        # --- import optional heavy deps inside the thread ---
        try:
            import numpy as np
            import sounddevice as sd
            import webrtcvad
        except ImportError as e:
            self.error_occurred.emit(
                f"Missing library: {e}. "
                "Install: pip install sounddevice webrtcvad-wheels openwakeword numpy"
            )
            return

        print(f"[WAKE] Loading wake-word model '{self.wake_word}'...")
        try:
            import openwakeword as _oww_pkg
            from openwakeword.model import Model
            _oww_dir = os.path.dirname(_oww_pkg.__file__)
            _model_path = os.path.join(_oww_dir, "resources", "models", f"{self.wake_word}.onnx")
            if not os.path.exists(_model_path):
                _model_path = self.wake_word  # allow absolute path as fallback
            oww = Model(wakeword_model_paths=[_model_path])
        except Exception as e:
            self.error_occurred.emit(f"openWakeWord could not be loaded: {e}")
            return

        def _reset_wake_model():
            reset = getattr(oww, "reset", None)
            if callable(reset):
                try:
                    reset()
                except Exception:
                    pass

        vad = webrtcvad.Vad(3)  # aggressiveness 0-3; 3 = most aggressive (declares silence faster)

        from collections import deque
        import queue as _queue
        pre_roll = deque(maxlen=self.PRE_ROLL_BLOCKS)
        audio_q: _queue.Queue = _queue.Queue()

        def _audio_callback(indata, frames, time_info, status):
            audio_q.put(bytes(indata))

        try:
            stream = sd.RawInputStream(
                samplerate=self.DEVICE_RATE,
                channels=self.CHANNELS,
                dtype="int16",
                blocksize=self.BLOCK_SAMPLES,   # 3840 samples = 80 ms at 48kHz
                callback=_audio_callback,
            )
            stream.start()
        except Exception as e:
            self.error_occurred.emit(f"Microphone could not be opened: {e}")
            return

        recording    = False
        rec_blocks   = []
        silence_cnt  = 0
        speech_cnt   = 0
        onset_cnt    = 0
        cooldown_cnt = 0   # blocks to skip after wake-word (ding sound + echo)
        wake_hit_cnt = 0
        wake_reject_cnt = 0
        recent_speech_cnt = 0
        session_was_active = False

        vad_bytes = self.VAD_FRAME_SAMPLES * 2  # bytes per 30 ms VAD frame

        print(f"[WAKE] Ready. Say '{self.wake_word.replace('_v0.1', '')}' to start.")
        print(
            f"[WAKE] Microphone: {sd.query_devices(kind='input')['name']}  |  "
            f"Threshold: {self.ww_threshold}  |  Consecutive: {self.wake_consecutive_blocks}  |  "
            f"VAD gate: {'on' if self.wake_require_vad else 'off'}"
        )

        while self.running:
            try:
                block = audio_q.get(timeout=0.5)
            except _queue.Empty:
                continue

            # While AudioWorker is processing, drain mic silently
            if self._busy:
                pre_roll.clear()
                onset_cnt = 0
                wake_hit_cnt = 0
                wake_reject_cnt = 0
                recent_speech_cnt = 0
                continue

            # --- VAD: split 80 ms block into 30 ms sub-frames ---
            is_speech = False
            for i in range(0, len(block), vad_bytes):
                sub = block[i:i + vad_bytes]
                if len(sub) == vad_bytes:
                    try:
                        if vad.is_speech(sub, self.DEVICE_RATE):
                            is_speech = True
                            break
                    except Exception:
                        pass

            if is_speech:
                recent_speech_cnt = self.wake_vad_grace_blocks
            else:
                recent_speech_cnt = max(0, recent_speech_cnt - 1)

            # Session timeout, notify once.
            if session_was_active and not self._in_session() and not recording:
                self.session_expired.emit()
                session_was_active = False

            if not recording:
                pre_roll.append(block)
                in_session = self._in_session()

                # Wake-word check only while idle. During a follow-up session VAD
                # handles speech onset, otherwise false positives can ding-loop.
                ww_fired = False
                if not in_session and time.time() >= self._wake_disabled_until:
                    audio_np = np.frombuffer(block, dtype=np.int16)
                    try:
                        from scipy.signal import resample_poly
                        audio_16k = resample_poly(audio_np, 1, 3).astype(np.int16)
                        scores = oww.predict(audio_16k)
                        max_score = max(scores.values(), default=0.0)
                        above_threshold = max_score >= self.ww_threshold
                        speech_gate_open = (not self.wake_require_vad) or recent_speech_cnt > 0
                        if above_threshold and speech_gate_open:
                            wake_hit_cnt += 1
                            wake_reject_cnt = 0
                        elif above_threshold:
                            wake_hit_cnt = 0
                            wake_reject_cnt += 1
                            if self.wake_debug:
                                print(f"[WAKE] Ignored score {max_score:.2f} without VAD speech.")
                            if wake_reject_cnt >= self.wake_consecutive_blocks:
                                self.end_session(self.failed_wake_rearm_seconds)
                                _reset_wake_model()
                                wake_reject_cnt = 0
                        else:
                            wake_hit_cnt = 0
                            wake_reject_cnt = 0
                        ww_fired = wake_hit_cnt >= self.wake_consecutive_blocks
                    except Exception:
                        wake_hit_cnt = 0
                        wake_reject_cnt = 0
                else:
                    wake_hit_cnt = 0
                    wake_reject_cnt = 0

                # Session-mode speech onset
                if in_session:
                    session_was_active = True
                    onset_cnt = onset_cnt + 1 if is_speech else max(0, onset_cnt - 1)
                    session_trigger = onset_cnt >= self.ONSET_BLOCKS
                else:
                    onset_cnt = 0
                    session_trigger = False

                if ww_fired or session_trigger:
                    pause_media_for_voice()
                    if ww_fired:
                        self._play_ding()
                        _reset_wake_model()
                    self.wakeword_detected.emit()
                    recording    = True
                    rec_blocks   = []          # Start fresh, do not include "hey jarvis".
                    cooldown_cnt = 3 if ww_fired else 0  # skip ding/wake-word echo only
                    silence_cnt  = 0
                    speech_cnt   = 0
                    onset_cnt    = 0
                    wake_hit_cnt = 0
                    wake_reject_cnt = 0

            else:  # --- recording mode ---
                # Skip first few blocks so the ding sound isn't recorded
                if cooldown_cnt > 0:
                    cooldown_cnt -= 1
                    continue

                rec_blocks.append(block)
                if is_speech:
                    speech_cnt  += 1
                    silence_cnt  = 0
                else:
                    silence_cnt += 1

                ended     = silence_cnt >= self.silence_blocks and speech_cnt >= self.MIN_SPEECH_BLOCKS
                no_speech = silence_cnt >= self.no_speech_blocks and speech_cnt < self.MIN_SPEECH_BLOCKS
                too_long  = len(rec_blocks) >= self.MAX_BLOCKS

                if ended or no_speech or too_long:
                    recording = False
                    if speech_cnt >= self.MIN_SPEECH_BLOCKS:
                        import wave
                        fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="ww_")
                        os.close(fd)
                        with wave.open(wav_path, "wb") as wf:
                            wf.setnchannels(self.CHANNELS)
                            wf.setsampwidth(2)
                            wf.setframerate(self.DEVICE_RATE)
                            wf.writeframes(b"".join(rec_blocks))
                        self._busy = True
                        self.audio_ready.emit(wav_path)
                    elif no_speech:
                        self.session_expired.emit()
                    rec_blocks  = []
                    speech_cnt  = 0
                    silence_cnt = 0
                    if no_speech:
                        self.end_session(self.failed_wake_rearm_seconds)
                        _reset_wake_model()
                        session_was_active = False

        stream.stop()
        stream.close()


# --- Background Audio/API Worker Thread ---

class AudioWorker(QThread):
    transcription_done = pyqtSignal(str)
    finished = pyqtSignal(bool, str, str, str, str, dict)  # success, message, transcript, parsed_summary, action, parsed

    def __init__(self, audio_path, repeat_command_getter=None, last_transcript_getter=None, window_context_getter=None):
        super().__init__()
        self.audio_path = audio_path
        self.repeat_command_getter = repeat_command_getter
        self.last_transcript_getter = last_transcript_getter
        self.window_context_getter = window_context_getter

    def _summarize_parsed(self, parsed):
        action = parsed.get("action", "unbekannt")
        parts = [action]

        app = parsed.get("app_name") or parsed.get("target")
        if app:
            parts.append(str(app))

        target = parsed.get("target")
        if action in ("set_volume", "set_app_volume", "set_brightness") and target:
            parts.append(str(target))

        layout = parsed.get("layout")
        if layout:
            parts.append(layout)

        desktop = parsed.get("desktop")
        if desktop is not None:
            parts.append(f"Workspace {desktop + 1}")

        monitor = parsed.get("monitor")
        if monitor is not None:
            parts.append(f"Monitor {monitor}")

        return " · ".join(parts)

    def run(self):
        try:
            text = transcribe(self.audio_path)
            if not text:
                self.finished.emit(False, "Nothing understood or recording too short.", "", "", "", {})
                return

            self.transcription_done.emit(text)
            if is_sleep_command(text):
                self.finished.emit(True, "Okay, listening only for the wake word again.", text, "Wake word mode", "voice_sleep", {})
                return
            if is_wait_command(text):
                self.finished.emit(True, "Okay, I will stay awake for a moment.", text, "Session extended", "voice_wait", {})
                return
            if is_recall_command(text):
                last_text = self.last_transcript_getter() if self.last_transcript_getter else ""
                if last_text:
                    self.finished.emit(True, f'You said: "{last_text}"', text, "Last command", "voice_recall", {})
                else:
                    self.finished.emit(False, "I do not have a previous command saved yet.", text, "Last command", "voice_recall", {})
                return
            if is_repeat_command(text):
                repeat_text = self.repeat_command_getter() if self.repeat_command_getter else ""
                if not repeat_text:
                    self.finished.emit(False, "I do not have a matching volume or brightness command to repeat.", text, "Repeat", "voice_repeat", {})
                    return
                data = execute_command(repeat_text)
                parsed = data.get("parsed", {})
                parsed_summary = f"Repeat: {self._summarize_parsed(parsed)}"
                result = data.get("result", {})
                success = result.get("success", False)
                msg = result.get("message", "Command repeated.")
                self.finished.emit(success, msg, text, parsed_summary, "voice_repeat", parsed)
                return

            context = self.window_context_getter() if self.window_context_getter else None
            handled, expanded_or_message = _contextual_window_command(text, context)
            command_text = expanded_or_message
            if handled and not command_text.startswith(("verschiebe ", "schließe ")):
                self.finished.emit(False, command_text, text, "Context", "voice_context", {})
                return
            if not handled:
                command_text = text

            # 2. Dispatch transcribed command directly to Backend API
            data = execute_command(command_text)
            parsed = data.get("parsed", {})
            parsed_summary = self._summarize_parsed(parsed)
            if handled:
                parsed_summary = f"Context: {parsed_summary}"
            action = parsed.get("action", "")
            result = data.get("result", {})
            success = result.get("success", False)
            msg = result.get("message", "Command executed.")
            self.finished.emit(success, msg, text, parsed_summary, action, parsed)

        except requests.exceptions.ConnectionError:
            self.finished.emit(False, "Backend offline. Is main.py running?", "", "", "", {})
        except Exception as e:
            self.finished.emit(False, str(e), "", "", "", {})
        finally:
            try:
                os.remove(self.audio_path)
            except OSError:
                pass


# --- Unified Voice Assistant Application Controller ---

class VoiceAssistantApp:
    def __init__(self, keyboards, wake_word_mode=False, wake_word="hey_jarvis_v0.1"):
        self.keyboards = keyboards

        # Cooldown to prevent duplicate triggers from multiple virtual evdev devices
        self.last_trigger_time = 0.0
        self.cooldown_seconds = 0.4

        # Create transparent Overlay HUD window
        self.overlay = OverlayWindow()

        # State tracking
        self.is_recording = False
        self.rec_proc = None
        self.rec_path = None
        self.worker = None
        self.last_repeatable_command = ""
        self.last_user_transcript = ""
        self.last_window_context = None
        self.last_window_move_back_command = ""

        # Wake-Word thread (optional)
        self.wake_word_thread = None
        self._result_shown_at = 0.0   # timestamp when last result was displayed
        if wake_word_mode:
            self.wake_word_thread = WakeWordThread(wake_word)
            self.wake_word_thread.wakeword_detected.connect(self.on_wakeword_detected)
            self.wake_word_thread.audio_ready.connect(self.on_wake_audio_ready)
            self.wake_word_thread.session_expired.connect(self.on_session_expired)
            self.wake_word_thread.error_occurred.connect(self.on_wakeword_error)
            self.wake_word_thread.start()

            # Poll every second. If session is active and result display is done, show "Ready...".
            self._session_poll = QTimer()
            self._session_poll.setInterval(1000)
            self._session_poll.timeout.connect(self._poll_session_hud)
            self._session_poll.start()

        # Keyboard thread always available as push-to-talk fallback
        self.listener_thread = KeyboardListenerThread(self.keyboards)
        self.listener_thread.key_pressed.connect(self.on_hotkey_triggered)
        self.listener_thread.start()

    def on_hotkey_triggered(self):
        current_time = time.time()
        if current_time - self.last_trigger_time < self.cooldown_seconds:
            return  # Ignore duplicate trigger within cooldown period
        self.last_trigger_time = current_time

        if not self.is_recording:
            # Start recording state
            pause_media_for_voice()
            fd, self.rec_path = tempfile.mkstemp(suffix=".wav", prefix="assistant_")
            os.close(fd)
            self.rec_proc = subprocess.Popen(
                ["arecord", "-f", "cd", "-t", "wav", self.rec_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            self.is_recording = True
            self.overlay.show_overlay("listening", "Listening...")
        else:
            # Stop recording and process
            if self.rec_proc:
                self.rec_proc.terminate()
                self.rec_proc.wait()
            self.rec_proc = None
            self.is_recording = False

            self.overlay.update_state("processing", "Understanding audio...")
            
            # Dispatch background transcription & execution threads
            self.worker = AudioWorker(
                self.rec_path,
                self.get_repeatable_command,
                self.get_last_user_transcript,
                self.get_window_context,
            )
            self.worker.transcription_done.connect(self.on_transcription_received)
            self.worker.finished.connect(self.on_process_completed)
            self.worker.start()

    # --- Wake-Word callbacks ---

    def on_wakeword_detected(self):
        """Wake word fired, or session onset, so show the HUD."""
        self.overlay.show_overlay("listening", "Listening...")

    def on_wake_audio_ready(self, path):
        """Wake-word thread recorded speech, hand off to AudioWorker."""
        self.overlay.update_state("processing", "Understanding audio...")
        self.worker = AudioWorker(
            path,
            self.get_repeatable_command,
            self.get_last_user_transcript,
            self.get_window_context,
        )
        self.worker.transcription_done.connect(self.on_transcription_received)
        self.worker.finished.connect(self.on_process_completed)
        self.worker.start()

    def on_session_expired(self):
        """Session timed out, hide the HUD."""
        self.overlay.hide_overlay()
        resume_media_after_voice()

    def _poll_session_hud(self):
        """Every second, transition the result into session color or hide when done."""
        wt = self.wake_word_thread
        if not wt:
            return
        if self._result_shown_at is None:
            return  # TTS still playing, keep green until speech finishes.
        result_done = time.time() - self._result_shown_at > 2.0
        if not result_done:
            return
        current_state = self.overlay.orb.state
        if current_state not in ("success", "error"):
            return  # already transitioned or in listening/processing state
        if wt._in_session():
            # Seamless color change to the session state without fade out/in.
            self.overlay.update_state("session", "Ready...")
        else:
            # No session, so now we can hide.
            self.overlay.hide_overlay()

    def on_wakeword_error(self, msg):
        print(f"[WAKE] {msg}")
        self.overlay.show_result(False, f"Wake-Word: {msg}")

    # --- Shared callbacks ---

    def on_transcription_received(self, text):
        self.overlay.update_state("processing", f'Understood:\n"{text}"')

    def get_repeatable_command(self):
        return self.last_repeatable_command

    def get_last_user_transcript(self):
        return self.last_user_transcript

    def get_window_context(self):
        if not self.last_window_context:
            return None
        return {
            **self.last_window_context,
            "move_back_command": self.last_window_move_back_command,
        }

    @staticmethod
    def _inverse_window_move_command(parsed):
        layout = parsed.get("layout")
        if layout == "right":
            return "verschiebe aktives fenster links"
        if layout == "left":
            return "verschiebe aktives fenster rechts"

        monitor = parsed.get("monitor")
        if monitor == 1:
            return "verschiebe aktives fenster auf linken monitor"
        if monitor == 0:
            return "verschiebe aktives fenster auf rechten monitor"

        from_desktop = parsed.get("from_desktop")
        if from_desktop is not None:
            return f"verschiebe aktives fenster auf arbeitsfläche {from_desktop + 1}"

        return ""

    def _remember_window_context(self, parsed):
        action = parsed.get("action")
        if action not in ("open_app", "open_url", "open_path", "move_window"):
            return
        window_class = parsed.get("window_class")
        app_ref = parsed.get("app_name") or parsed.get("target") or window_class
        if window_class:
            app_ref = window_class
        if not app_ref:
            return
        self.last_window_context = {
            "app_ref": app_ref,
            "app_name": parsed.get("app_name") or app_ref,
            "window_class": window_class,
            "window_title": parsed.get("window_title"),
        }
        if action == "move_window" and not parsed.get("restore_previous"):
            inverse = self._inverse_window_move_command(parsed)
            if inverse:
                self.last_window_move_back_command = inverse

    @staticmethod
    def _is_repeatable_action(action, parsed_summary):
        if action in ("set_volume", "set_app_volume"):
            return any(marker in parsed_summary for marker in (" +", " -"))
        if action == "set_brightness":
            return any(marker in parsed_summary for marker in ("Heller +", "Dunkler -"))
        return False

    def on_process_completed(self, success, message, transcript, parsed_summary, action, parsed):
        lines = []
        if transcript:
            lines.append(f'Heard: "{transcript}"')
        if parsed_summary:
            lines.append(f"Action: {parsed_summary}")
        lines.append(message)
        self.overlay.show_result(success, "\n".join(lines))
        # TTS actions: hold green until speech finishes (_speak_then_extend sets this)
        self._result_shown_at = None if (success and action in _SPEAK_ACTIONS and self.wake_word_thread) else time.time()
        if success and transcript and action not in {"voice_sleep", "voice_wait", "voice_repeat", "voice_recall"}:
            self.last_user_transcript = transcript
        if success and transcript and self._is_repeatable_action(action, parsed_summary):
            self.last_repeatable_command = transcript
        if success and parsed:
            self._remember_window_context(parsed)
        if success and action in ("media_control", "control_spotify"):
            forget_paused_media()  # User took explicit playback control, so stop auto-resume/pause.

        wt = self.wake_word_thread
        if action == "voice_sleep":
            if wt:
                wt.end_session()
            QTimer.singleShot(1200, self.overlay.hide_overlay)
            QTimer.singleShot(1200, resume_media_after_voice)
            return
        if action == "voice_wait":
            if wt:
                wt.set_busy(False)
                wt.extend_session(wt.local_wait_seconds)
                self.overlay.close_timer.stop()
            QTimer.singleShot(900, lambda: self.overlay.update_state("session", "Ready..."))
            return

        # When wake-word mode is active and command succeeded:
        # suppress the auto-hide so _poll_session_hud can do a seamless colour transition.
        if wt and success:
            self.overlay.close_timer.stop()

        if success and action in _SPEAK_ACTIONS:
            def _speak_then_extend():
                speak(message, response_lang=(parsed or {}).get("lang", "en"))
                self._result_shown_at = time.time()  # TTS done, start 2 s countdown to "Ready..."
                if wt:
                    wt.set_busy(False)
                    wt.extend_session()
                else:
                    resume_media_after_voice()
            threading.Thread(target=_speak_then_extend, daemon=True).start()
        else:
            if wt:
                def _finish_wake_cycle():
                    time.sleep(0.8)
                    wt.set_busy(False)
                    wt.extend_session()  # on error: keep session open so user can retry
                threading.Thread(target=_finish_wake_cycle, daemon=True).start()
            else:
                resume_media_after_voice()

    def shutdown(self):
        if self.wake_word_thread:
            self.wake_word_thread.stop()
            self.wake_word_thread.wait()
        self.listener_thread.stop()
        self.listener_thread.wait()
        if self.rec_proc:
            self.rec_proc.terminate()
            self.rec_proc.wait()


def main():
    import argparse
    load_env()
    global HUD_STYLE, HUD_POSITION, HOTKEY
    HUD_STYLE = os.environ.get("HUD_STYLE", "kompanion").lower()
    HUD_POSITION = os.environ.get("HUD_POSITION", "bottom-right").lower()
    _hotkey_name = os.environ.get("HOTKEY_KEY", "KEY_RIGHTCTRL").strip()
    HOTKEY = getattr(ecodes, _hotkey_name, ecodes.KEY_RIGHTCTRL)
    os.environ["QT_QPA_PLATFORM"] = "xcb"
    stt_key = os.environ.get("STT_API_KEY", "")
    whisper_url = os.environ.get("WHISPER_BASE_URL", "")
    if not whisper_url and not stt_key:
        print("Error: no STT configured. Set STT_API_KEY or WHISPER_BASE_URL.")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Local Assistant voice listener")
    parser.add_argument("--wakeword", action="store_true",
                        help="Enable wake-word mode with openWakeWord and VAD")
    parser.add_argument("--wake-word-model",
                        default=os.environ.get("WAKE_WORD", "hey_jarvis_v0.1"),
                        help="openWakeWord model name. Default: hey_jarvis_v0.1")
    args = parser.parse_args()

    # Also respect WAKE_WORD_ENABLED=1 in .env
    wake_word_mode = args.wakeword or os.environ.get("WAKE_WORD_ENABLED", "0") == "1"

    keyboards = find_keyboards()
    if not keyboards and not wake_word_mode:
        print(f"Error: no keyboard with '{_hotkey_name}' found.")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    if wake_word_mode:
        print(f"Wake-word mode active. Model: {args.wake_word_model}")
        print("Right Ctrl is still available as push-to-talk.")
    else:
        print(f"Kompanion overlay listener active on {len(keyboards)} keyboard(s).")
        print("Right Ctrl starts, stops and runs voice control.")
    print("Press Ctrl+C in the terminal to exit.")

    controller = VoiceAssistantApp(keyboards,
                                   wake_word_mode=wake_word_mode,
                                   wake_word=args.wake_word_model)

    # Graceful exit signal handler
    import signal
    def sigint_handler(*args):
        print("\nStopping Kompanion overlay listener...")
        controller.shutdown()
        app.quit()
        sys.exit(0)
        
    signal.signal(signal.SIGINT, sigint_handler)

    # Keep Python signal handler responsive inside Qt event loop
    timer = QTimer()
    timer.start(200)
    timer.timeout.connect(lambda: None)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
