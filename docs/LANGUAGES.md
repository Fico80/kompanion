# Adding a Language

The assistant currently supports English and German through Python-based command parsers, response helpers and lightweight language detection.

This document describes the intended direction for adding more languages. The goal is to move common command words, date words and response text into language files over time while keeping the parser pipeline deterministic.

## Current State

Language handling currently lives in:

```text
backend/shared/i18n.py
backend/parser.py
backend/capabilities/*/parser.py
backend/capabilities/*/executor.py
```

`backend/shared/i18n.py` detects the command language and adds `lang` to parsed commands. Executors use that value to choose response text.

Supported response languages today:

```text
en
de
```

## Current Manual Process

Until `config/languages/*.json` is implemented, adding a language means updating the Python parsers and response helpers directly.

Assume you want to add French with language code `fr`.

### 1. Add Language Detection

Edit:

```text
backend/shared/i18n.py
```

Add a word set for the new language:

```python
FR_WORDS = {
    "ouvre", "lance", "ferme", "fenêtre", "gauche", "droite",
    "volume", "plus", "moins", "muet", "météo", "calendrier",
    "rappel", "aujourd", "demain", "fichier", "dossier",
}
```

Then update `detect_language()` so it scores the new language and returns `"fr"` when French has the highest score.

Keep the default as English unless there is a strong reason to change it.

### 2. Add Parser Synonyms

Add language-specific command words in the capability parsers.

Common files:

```text
backend/parser.py
backend/capabilities/audio/parser.py
backend/capabilities/brightness/parser.py
backend/capabilities/calendar/parser.py
backend/capabilities/clipboard/parser.py
backend/capabilities/notes/parser.py
backend/capabilities/search/parser.py
backend/capabilities/tasks/parser.py
backend/capabilities/timer/parser.py
backend/capabilities/weather/parser.py
backend/capabilities/windows/parser.py
```

Start with the important ones:

```text
windows/parser.py       close, move, active window, workspace
audio/parser.py         volume, mute, media control
calendar/parser.py      event creation, calendar queries, weekdays, months
tasks/parser.py         add/query/complete tasks, relative dates
search/parser.py        file/folder search
```

Example:

```python
# before
r"\b(open|start|öffne|starte)\b"

# after
r"\b(open|start|öffne|starte|ouvre|lance)\b"
```

Prefer narrow command phrases over broad words. Broad words cause accidental matches.

### 3. Add Date Words

Calendar and task parsing need relative date words, weekdays and month names.

Edit:

```text
backend/capabilities/calendar/parser.py
backend/capabilities/tasks/parser.py
```

Add:

```python
"lundi": 0,
"mardi": 1,
"mercredi": 2,
```

and:

```python
"janvier": 1,
"février": 2,
"mars": 3,
```

Also add relative date phrases:

```text
today      -> aujourd'hui
tomorrow   -> demain
this week  -> cette semaine
next week  -> semaine prochaine
```

Make sure the returned labels are in the same language as the command. For example, a French command should not return `"tomorrow"` as `task_due_label`.

### 4. Add Response Text

Executors return user-facing messages. Add `fr` branches where responses are currently selected by `lang(parsed)`.

Common files:

```text
backend/executor.py
backend/main.py
backend/capabilities/audio/executor.py
backend/capabilities/brightness/executor.py
backend/capabilities/calendar/executor.py
backend/capabilities/clipboard/executor.py
backend/capabilities/notes/executor.py
backend/capabilities/search/executor.py
backend/capabilities/spotify/executor.py
backend/capabilities/system/executor.py
backend/capabilities/tasks/executor.py
backend/capabilities/timer/executor.py
backend/capabilities/weather/executor.py
backend/capabilities/windows/executor.py
```

Example pattern:

```python
if response_lang == "de":
    message = "Aufgabe notiert: {task}"
elif response_lang == "fr":
    message = "Tâche enregistrée : {task}"
else:
    message = "Task saved: {task}"
```

Keep English as the fallback.

### 5. Update LLM Prompts

Some features ask the LLM to produce text:

```text
backend/capabilities/clipboard/executor.py
backend/capabilities/notes/executor.py
```

Add prompts that explicitly request the new language:

```text
Réponds uniquement en français.
```

Do not rely on the model to infer the language from the input.

### 6. Add Tests

Add parser tests in:

```text
tests/test_parser.py
tests/test_features.py
```

At minimum, test:

```text
open app
multi-open
move window
close all windows
create calendar event
add task with tomorrow
query tasks
complete task
system query
```

Also assert `lang == "fr"` for representative commands.

Run:

```bash
python3 -m unittest tests/test_parser.py tests/test_features.py
python3 -m py_compile backend/parser.py backend/executor.py backend/main.py backend/capabilities/*/parser.py backend/capabilities/*/executor.py scripts/listener.py
```

## Planned Language File Layout

Future language packs should live in:

```text
config/languages/en.json
config/languages/de.json
config/languages/fr.json
```

Example:

```json
{
  "meta": {
    "code": "en",
    "name": "English"
  },
  "commands": {
    "open": ["open", "start", "show"],
    "close": ["close", "quit", "exit"],
    "move": ["move", "send", "push"],
    "volume_up": ["volume up", "louder", "turn up"],
    "volume_down": ["volume down", "quieter", "turn down"],
    "mute": ["mute", "sound off"],
    "unmute": ["unmute", "sound on"]
  },
  "dates": {
    "today": ["today"],
    "tomorrow": ["tomorrow"],
    "day_after_tomorrow": ["day after tomorrow"],
    "weekdays": {
      "monday": 0,
      "tuesday": 1,
      "wednesday": 2,
      "thursday": 3,
      "friday": 4,
      "saturday": 5,
      "sunday": 6
    },
    "months": {
      "january": 1,
      "february": 2,
      "march": 3,
      "april": 4,
      "may": 5,
      "june": 6,
      "july": 7,
      "august": 8,
      "september": 9,
      "october": 10,
      "november": 11,
      "december": 12
    }
  },
  "responses": {
    "cancelled": "Cancelled.",
    "not_understood": "Command not understood.",
    "task_saved": "Task saved: {task}",
    "task_saved_due": "Task saved: {task} (by {due})",
    "no_open_tasks": "No open tasks. All done!",
    "event_created": "Event created: {name}, {date}.",
    "no_events": "No events {range}.",
    "all_windows_closed": "All windows closed.",
    "window_moved_back": "Window moved back.",
    "volume_changed": "Volume changed.",
    "brightness_changed": "Brightness {target}: {value}."
  }
}
```

## Suggested Steps for a New Language

1. Add language detection keywords in `backend/shared/i18n.py`.
2. Add parser synonyms for the new language in the relevant capability parsers.
3. Add response strings in the relevant executors.
4. Add date words, weekdays and month names in calendar and task parsers.
5. Add examples to `README.md`.
6. Add parser tests for the new language.

## Minimum Useful Coverage

A new language should cover these workflows first:

```text
open app
open app left/right
open app and app
move window left/right/workspace
close app
close all windows
volume up/down/mute
create calendar event
query calendar
add task
query tasks
complete task
search files
local session commands
```

## Parser Tests

Add tests for both parsing and response language. Good starter cases:

```text
open Firefox left
open Firefox and Discord
move Firefox to workspace 2
close all windows
create event dentist tomorrow at 3 pm
remind me tomorrow to pay the bill
show my tasks
what is my RAM usage
```

For a new language, add equivalent examples and assert:

- `action`
- important target fields
- `lang`
- response text for at least tasks, calendar, windows and system queries

## Design Notes

Keep the parser deterministic. Language files should provide vocabulary and response templates, but they should not turn the assistant into a free-form LLM router.

When a phrase is ambiguous, prefer explicit command patterns over broad matching. A small number of reliable commands is better than many fuzzy commands that trigger accidentally.

The long-term shape should be:

```text
config/languages/*.json
-> shared language loader
-> capability parsers
-> parsed lang
-> localized executor responses
```
