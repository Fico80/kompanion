# Security Notes

This assistant controls local desktop actions such as opening apps, opening files, moving windows, reading the clipboard and creating calendar events. Treat it as a local automation tool, not as a public web service.

## Before Publishing Or Running

- Keep `.env` private. It may contain API keys and OAuth client secrets.
- Keep the backend bound to `127.0.0.1` unless you fully understand the risk.
- Do not expose port `8000` to a network or the internet.
- Only use trusted STT and LLM endpoints. Voice commands, file names, clipboard text and note content may be sent to those services depending on the command.
- Review OAuth scopes before connecting Spotify or Google Calendar.
- Do not commit local data under `data/` or token files under `~/.config/lokaler-assistent/`.

## Local API

The local API can execute desktop actions through `/api/execute`. By default, CORS is restricted to the local frontend origins:

```text
http://127.0.0.1:8000
http://localhost:8000
```

If you need custom browser origins, set:

```bash
ASSISTANT_CORS_ORIGINS=http://127.0.0.1:8000,http://localhost:8000
```

Avoid using `*` for CORS because a malicious webpage could otherwise try to drive the local assistant from the browser.

## OAuth Tokens

Spotify and Google Calendar tokens are stored under:

```text
~/.config/lokaler-assistent/
```

The application writes token directories as `0700` and token files as `0600` where the platform allows it.

## Reporting Issues

If you publish the project, ask users to avoid posting real API keys, OAuth client secrets, access tokens, refresh tokens, private file paths or command history in bug reports.
