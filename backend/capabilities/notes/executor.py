import os
import re
from datetime import datetime, timedelta

from shared.llm import llm_complete
from shared.i18n import lang
from shared.paths import NOTES_DIR


_NOTE_TIME_LABELS = {
    "today": "heute",
    "yesterday": "gestern",
    "week": "der letzten Woche",
    "month": "des letzten Monats",
}
_NOTE_TIME_LABELS_EN = {
    "today": "today",
    "yesterday": "yesterday",
    "week": "from the last week",
    "month": "from the last month",
}
_NOTE_TIME_DAYS = {"today": 1, "yesterday": 2, "week": 7, "month": 30}


def query_notes(parsed: dict) -> dict:
    import memory as _mem

    response_lang = lang(parsed)
    mode = parsed.get("note_mode", "search")
    topic = (parsed.get("target") or "").strip() or None
    time_filter = parsed.get("time_filter")

    if topic:
        notes = _mem.search_notes(topic, top_k=8)
        if time_filter:
            cutoff = (datetime.now() - timedelta(days=_NOTE_TIME_DAYS.get(time_filter, 7))).isoformat()
            notes = [n for n in notes if n["ts"] > cutoff]
    elif time_filter:
        notes = _mem.get_notes_since(_NOTE_TIME_DAYS.get(time_filter, 7))
    else:
        notes = _mem.get_notes(15)

    scope = ""
    if topic:
        scope += f" zu '{topic}'" if response_lang == "de" else f" about '{topic}'"
    if time_filter:
        labels = _NOTE_TIME_LABELS if response_lang == "de" else _NOTE_TIME_LABELS_EN
        scope += f" von {labels.get(time_filter, time_filter)}" if response_lang == "de" else f" {labels.get(time_filter, time_filter)}"

    if not notes:
        msg = f"Keine Notizen{scope} gefunden." if response_lang == "de" else f"No notes{scope} found."
        return {"success": True, "message": msg}

    context = "\n".join(f"- ({n['ts'][:10]}) {n['content']}" for n in notes[:8])

    if mode == "summarize":
        if response_lang == "de":
            prompt = (
                "Fasse die folgenden persönlichen Notizen auf Deutsch in 3-5 Sätzen zusammen. "
                "Nenne die wichtigsten Punkte. Antworte NUR mit der Zusammenfassung:\n\n" + context
            )
        else:
            prompt = (
                "Summarize the following personal notes in English in 3-5 sentences. "
                "Mention the most important points. Reply ONLY with the summary:\n\n" + context
            )
    else:
        if response_lang == "de":
            frage = f"Was habe ich{scope} notiert?" if scope else "Worum geht es in meinen Notizen?"
            prompt = (
                f"Beantworte die folgende Frage NUR anhand der Notizen, auf Deutsch, kurz und konkret. "
                f"Wenn die Notizen nichts dazu hergeben, sag das ehrlich.\n\n"
                f"Frage: {frage}\n\nNotizen:\n{context}"
            )
        else:
            question = f"What did I note{scope}?" if scope else "What are my notes about?"
            prompt = (
                f"Answer the following question ONLY based on the notes, in English, briefly and concretely. "
                f"If the notes do not contain the answer, say so honestly.\n\n"
                f"Question: {question}\n\nNotes:\n{context}"
            )

    answer = llm_complete(prompt)
    if answer:
        return {"success": True, "message": answer, "details": {"note_count": len(notes)}}

    listing = "\n".join(f"• {n['content'][:90]}" for n in notes[:5])
    count = len(notes)
    header = f"{count} Notiz{'en' if count != 1 else ''}{scope}:" if response_lang == "de" else f"{count} note{'s' if count != 1 else ''}{scope}:"
    return {
        "success": True,
        "message": f"{header}\n{listing}",
    }


def _append_backlink(note_path: str, link_name: str) -> None:
    try:
        with open(note_path, "r", encoding="utf-8") as f:
            text = f.read()
        new_link = f"[[{link_name}]]"
        if new_link in text:
            return
        if "**Verwandte Notizen**" in text:
            text = text.rstrip() + f"\n- {new_link}\n"
        else:
            text = text.rstrip() + f"\n\n---\n**Verwandte Notizen**\n- {new_link}\n"
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


def _format_note(raw: str, response_lang: str) -> str:
    if response_lang == "de":
        prompt = (
            "Du bekommst einen diktierten Text. Formatiere ihn als saubere, gut lesbare Markdown-Notiz auf Deutsch.\n"
            "Regeln:\n"
            "- Erkenne die Art des Inhalts und wähle das passende Format.\n"
            "- Nummerierte oder aufgezählte Punkte → nummerierte Markdown-Liste.\n"
            "- Bei Listen: den Kernbegriff jedes Punktes **fett** schreiben. Kurze Erklärung (1 Satz) → Gedankenstrich in derselben Zeile. Längere Erklärung → in einer neuen Zeile darunter, mit einer Leerzeile zwischen den Punkten.\n"
            "- Wenn ein sinnvoller Titel erkennbar ist, diesen als ## Überschrift voranstellen.\n"
            "- Fließtext → saubere Absätze mit korrekter Interpunktion.\n"
            "- Wiederholungen und Füllwörter aus der Spracherkennung entfernen.\n"
            "- Keine Erklärungen, keine Einleitung — NUR der fertige Notiztext.\n\n"
            + raw
        )
    else:
        prompt = (
            "You receive dictated text. Format it as a clean, readable Markdown note in English.\n"
            "Rules:\n"
            "- Detect the type of content and choose the appropriate format.\n"
            "- Numbered or enumerated items → numbered Markdown list.\n"
            "- For lists: write the key term of each item in **bold**. Short explanation (1 sentence) → em dash on the same line. Longer explanation → new line below, with a blank line between items.\n"
            "- If a clear title is recognizable, add it as a ## heading.\n"
            "- Prose → clean paragraphs with correct punctuation.\n"
            "- Remove repetitions and filler words from speech recognition.\n"
            "- No explanations, no introduction — ONLY the finished note text.\n\n"
            + raw
        )
    formatted = llm_complete(prompt, max_tokens=1024)
    return formatted.strip() if formatted else raw


def save_note(content: str, response_lang: str = "en") -> dict:
    import memory as _mem

    content = _format_note(content, response_lang)

    notes_dir = str(NOTES_DIR)
    os.makedirs(notes_dir, exist_ok=True)
    now = datetime.now()
    slug = re.sub(r"[^\w\s-]", "", content[:30]).strip().replace(" ", "-")
    filename = f"{now.strftime('%Y-%m-%d_%H-%M')}_{slug}.md"
    link_name = filename[:-3]
    path = os.path.join(notes_dir, filename)

    # 1. Find similar notes BEFORE touching the DB (so this note doesn't match itself).
    similar = _mem.find_similar_notes(content)

    # 2. Write the file to disk first. Only record in the DB once the file exists.
    body = f"# {now.strftime('%Y-%m-%d %H:%M')}\n\n{content}\n"
    if similar:
        links = "\n".join(
            f"- [[{os.path.basename(s['path'])[:-3]}]] ({int(s['similarity'] * 100)}%)"
            for s in similar
            if s.get("path")
        )
        if links:
            body += f"\n---\n**Verwandte Notizen**\n{links}\n"

    with open(path, "w", encoding="utf-8") as f:
        f.write(body)

    # 3. Record in DB only after the file is successfully written.
    _mem.record_note(content, path)

    for s in similar:
        if s.get("path"):
            _append_backlink(s["path"], link_name)

    short = content[:50] + ("…" if len(content) > 50 else "")
    message = f"Notiz gespeichert: {short}" if response_lang == "de" else f"Note saved: {short}"
    if similar:
        refs = ", ".join(f"'{s['content'][:35]}'" for s in similar)
        message += f" — Ähnlich: {refs}" if response_lang == "de" else f" — Similar: {refs}"
    return {"success": True, "message": message, "details": {"path": path, "similar": similar}}


def _split_append(text: str) -> tuple[str, str]:
    import json as _json
    result = llm_complete(
        f"Extract the note title and new content from this voice command.\n"
        f"Reply ONLY as JSON: {{\"query\": \"...\", \"content\": \"...\"}}\n\n{text}",
        max_tokens=128,
    )
    if result:
        try:
            m = re.search(r'\{.*\}', result, re.DOTALL)
            if m:
                data = _json.loads(m.group())
                q, c = data.get("query", ""), data.get("content", "")
                if q and c:
                    return q, c
        except Exception:
            pass
    # Fallback: split on first sentence boundary (Whisper adds punctuation)
    sentence_m = re.match(r'^(.+?)[.!?,]\s+(.+)$', text, re.DOTALL)
    if sentence_m:
        return sentence_m.group(1).strip(), sentence_m.group(2).strip()
    # Last resort: first 3 words as query
    words = text.split()
    return " ".join(words[:3]), " ".join(words[3:])


def append_note(query: str, addition: str, response_lang: str = "en") -> dict:
    import memory as _mem
    if not query:
        query, addition = _split_append(addition)
        if not query:
            msg = "Konnte Notiztitel nicht erkennen." if response_lang == "de" else "Could not identify note title."
            return {"success": False, "message": msg}
    results = _mem.search_notes(query, top_k=1)
    if not results:
        msg = f"Keine Notiz gefunden für '{query}'." if response_lang == "de" else f"No note found for '{query}'."
        return {"success": False, "message": msg}
    path = results[0].get("path")
    if not path or not os.path.exists(path):
        msg = "Notiz-Datei nicht gefunden." if response_lang == "de" else "Note file not found."
        return {"success": False, "message": msg}
    addition = _format_note(addition, response_lang)
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n{addition}\n")
    # Re-embed the full note content so search stays accurate.
    # Do NOT insert a new DB row — one row per file.
    try:
        with open(path, encoding="utf-8") as f:
            full_content = f.read()
        _mem.update_note_embedding(path, full_content)
    except Exception:
        pass
    short = addition[:50] + ("…" if len(addition) > 50 else "")
    name = os.path.basename(path)
    msg = (f"Ergänzt in '{name}': {short}" if response_lang == "de"
           else f"Added to '{name}': {short}")
    return {"success": True, "message": msg}


def execute(parsed: dict) -> dict | None:
    action = parsed.get("action")
    if action == "save_note":
        return save_note(parsed.get("target") or "", lang(parsed))
    if action == "append_note":
        return append_note(parsed.get("note_query") or "", parsed.get("target") or "", lang(parsed))
    if action == "query_notes":
        return query_notes(parsed)
    return None
