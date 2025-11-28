# tgreports package guide

Documentation for the `tgreports` library (Telegram logging + alerting). Copy this file into a project's `docs/` folder so code-writing tools know how to use the package correctly.

## What it does
- Provides async helpers that both write to log files and send formatted messages to a Telegram chat.
- Uses the bundled `log.conf` unless a `log.conf` is present in the working directory (override by dropping your own file next to the app entrypoint).
- Serializes extra payloads safely and drops `None` fields to keep messages compact.
- Annotates Telegram messages with the runtime mode, severity emoji, source path/line, and hashtags for filtering.

## Installation
```bash
pip install tgreports
```
Also install its dependency `tgio` if your environment does not resolve it automatically.

## Quick start
```python
import asyncio
from tgreports import Report

MODE = "DEV"            # e.g. LOCAL / TEST / DEV / PRE / PROD
BOT_TOKEN = "123:ABC"   # Telegram bot token
BUG_CHAT = -100111222   # Target chat/channel id

report = Report(MODE, BOT_TOKEN, BUG_CHAT)

async def main():
    await report.info("Service started")                     # Telegram only in PRE/PROD
    await report.warning("Cache miss", tags=["cache"])
    try:
        1 / 0
    except Exception as exc:
        await report.error("Division failed", error=exc)     # Sends traceback

asyncio.run(main())
```
All public methods except `debug` are `async`; call them inside an event loop (`asyncio.run`, background task, or framework handler).

## API surface and behavior
- `Report(MODE, token, bug_chat)`: create a reporter with a mode label, bot token, and target chat id.
- `await report.debug(text, extra=None)`: file log only; never sent to Telegram.
- `await report.info(text, extra=None, tags=None, silent=False)`: info-level log. **Telegram send happens only when `mode` is `PRE` or `PROD`** (anti-noise rule). Set `silent=True` to log without Telegram.
- `await report.warning(...)`, `await report.error(...)`, `await report.critical(...)`: log + Telegram with stack traces (unless `silent=True`). Pass `error=<Exception>` to include the traceback; otherwise caller info is used.
- `await report.important(...)`: for significant user actions; no traceback in the Telegram message.
- `await report.request(...)`: for actionable user requests; no traceback.

### Message formatting rules (Telegram)
- Prefix: emoji + `{MODE} {TYPE}` (e.g. `⚠️ DEV WARNING`).
- Source context: best-effort `filename:line` and dotted path from the call stack/traceback, skipped for `info`/`important`/`request`.
- Extra data: if `extra` is a dict it is rendered as `key = value` lines; non-dicts are stringified.
- Tags: `#{mode.lower()}` is always added plus any `tags` you pass; use tags for filtering in the Telegram client.
- Automatic escalation: if `extra` contains `{"name": "Error"}` or `{"title": "Error"}`, the message is treated as an error even when sent via `info`.

### Data serialization specifics
- Dict `extra` values that are `None` are dropped; other values are JSON-encoded when possible, otherwise converted to `str`.
- Passing raw exception objects in `extra` works; they are stringified if JSON encoding fails.
- Sets and tuples inside `extra` are stringified (not JSON arrays); adjust upstream if strict JSON is required.

## Logging configuration
- On import, `logging.config.fileConfig` loads `log.conf` from the working directory if present; otherwise it falls back to the packaged `tgreports/log.conf`.
- Default destinations: `app.log` receives `DEBUG+`, `app.err` receives `WARNING+`, both opened in append mode (no size-based rotation configured).
- To change paths, rotation, or formats, supply your own `log.conf` beside the running process:
  ```ini
  [handler_logfile]
  class=handlers.RotatingFileHandler
  level=DEBUG
  args=('/var/log/myapp.log', 'a', 10_000_000, 5)
  formatter=logfileformatter
  ```

## Patterns and caveats
- Keep a single `Report` instance per service/process and import it where needed; avoids repeated Telegram auth setup.
- Use `silent=True` when you only want the log file side-effects (e.g., noisy loops, health checks).
- Because `info` messages skip Telegram outside `PRE`/`PROD`, use `warning`+ for anything that must alert in lower environments.
- The library is async end-to-end; calling from synchronous code requires wrapping with `asyncio.run` or scheduling with `asyncio.create_task`.
- Telegram failures are logged to `app.err` but do not raise; if alerts must be guaranteed, add your own retries/wrappers.

## Example patterns
```python
# Attach structured context
await report.request("Manual payout requested", extra={"user_id": 42, "amount": "100 USD"}, tags=["billing"])

# Promote a front-end error payload to an error-level alert
await report.info("Client error forwarded", extra={"title": "Error", "data": payload})

# Log only (no Telegram)
await report.important("Daily ETL finished", extra={"rows": 123_456}, silent=True)
```

## Testing locally
- The package ships with `tests/test_all.py` showing expected usage.
- Provide a valid bot token/chat id in tests or stub `Telegram.send` to avoid hitting Telegram during automated runs.
