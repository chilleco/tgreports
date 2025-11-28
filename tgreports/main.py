"""Telegram reporting helpers: logs to files and sends Telegram notifications.

- Configures Loguru sinks for `.log` (DEBUG/INFO) and `.err` (WARNING+) files
  when ``Report`` is initialized; file names are customizable.
- Provides async helpers that both write to log files and push formatted messages
  to a Telegram chat using `tgio.Telegram`.
"""

import json
import inspect
import traceback
from pathlib import Path

from loguru import logger
from tgio import Telegram


SYMBOLS = ["💬", "🟢", "⚠️", "❗️", "‼️", "✅", "🛎"]
TYPES = [
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
    "CRITICAL",
    "IMPORTANT",
    "REQUEST",
]


def to_json(data):
    """Convert any type to a JSON-serializable string; fall back to ``str``."""

    if isinstance(data, str):
        return data

    try:
        return json.dumps(data, ensure_ascii=False)
    except TypeError:
        return str(data)


def dump(data):
    """Normalize extra payloads for logging/Telegram messages.

    Drops keys with ``None`` values when given a dict, JSON-encodes values when
    possible, otherwise stringifies them.
    """

    if data is None:
        return None

    if not isinstance(data, dict):
        return str(data)

    return {k: to_json(v) for k, v in data.items() if v is not None}


class Report:
    """Bridge between Python logging and Telegram alerts.

    Creates formatted messages with mode, severity emoji, source info, and tags,
    writes to file handlers, and (depending on severity/mode) sends to Telegram.
    """

    _log_sink_id = None
    _err_sink_id = None
    _log_path = None
    _err_path = None
    _log_format = "[{time:YYYY-MM-DD HH:mm:ss}] {level.name} [{thread}] - {message}"

    def __init__(self, mode, token, bug_chat, log_file="app.log", err_file="app.err"):
        """Initialize a reporter.

        Args:
            mode: Environment label (e.g., LOCAL/TEST/DEV/PRE/PROD) used in
                messages and to gate info-level Telegram sends (only PRE/PROD).
            token: Telegram bot token.
            bug_chat: Target chat/channel id for notifications.
            log_file: Path to the debug/info log file.
            err_file: Path to the warning/error log file.
        """
        self.mode = mode or "TEST"
        self.tg = Telegram(token)
        self.bug_chat = bug_chat

        self._configure_logger(log_file, err_file)

    @classmethod
    def _configure_logger(cls, log_file, err_file):
        log_path = Path(log_file).expanduser()
        err_path = Path(err_file).expanduser()

        log_path.parent.mkdir(parents=True, exist_ok=True)
        err_path.parent.mkdir(parents=True, exist_ok=True)

        if (log_path, err_path) == (cls._log_path, cls._err_path):
            return

        if cls._log_sink_id is None and cls._err_sink_id is None:
            try:
                logger.remove(0)  # Drop default stderr sink to mirror file-only setup
            except ValueError:
                pass

        for sink_id in (cls._log_sink_id, cls._err_sink_id):
            if sink_id is not None:
                logger.remove(sink_id)

        cls._log_sink_id = logger.add(
            log_path,
            level="DEBUG",
            format=cls._log_format,
            filter=lambda record: record["level"].no < 30,  # Only DEBUG/INFO to .log
        )
        cls._err_sink_id = logger.add(
            err_path,
            level="WARNING",
            format=cls._log_format,
        )

        cls._log_path = log_path
        cls._err_path = err_path

    # pylint: disable=too-many-branches,too-many-locals,too-many-statements
    async def _report(
        self,
        text,
        type_=1,
        extra=None,
        tags=None,
        error=None,
    ):
        """Build and send a Telegram message based on severity and context.

        Adds mode/severity prefix, source path/line, dotted call path, extra
        payload, and hashtags. Handles traceback extraction when ``error`` is
        provided, and promotes info messages with ``extra`` name/title "Error"
        to error severity.
        """

        without_traceback = type_ in (1, 5, 6)

        if isinstance(extra, dict):
            if extra.get("name") == "Error":
                type_ = 3
                del extra["name"]

            if extra.get("title") == "Error":
                type_ = 3
                del extra["title"]

        if self.mode not in ("PRE", "PROD") and type_ == 1:
            return

        if not tags:
            tags = []

        if without_traceback:
            filename = None
            lineno = None
            function = None

        elif error:
            traces = traceback.extract_tb(error.__traceback__)[::-1]

            for trace in traces:
                if "python" not in trace.filename:
                    break
            else:
                trace = traces[0]

            filename = trace.filename
            lineno = trace.lineno
            function = trace.name

        else:
            previous = inspect.stack()[2]
            filename = previous.filename
            lineno = previous.lineno
            function = previous.function

        if filename:
            if filename[:4] == "/app":
                filename = filename[4:]
            if filename[:3] == "/./":
                filename = filename[3:]

            path = filename.replace("/", ".").split(".")[:-1]

            if path:
                if path[0] == "api":
                    path = path[1:]

                if function and function != "handle":
                    path.append(function)

                path = "\n" + ".".join(path)

            else:
                path = ""

            source = f"\n{filename}:{lineno}"

        else:
            path = ""
            source = ""

        text = f"{SYMBOLS[type_]} {self.mode} {TYPES[type_]}" f"{path}" f"\n\n{text}"

        if extra:
            if isinstance(extra, dict):
                extra_text = "\n".join(f"{k} = {v}" for k, v in extra.items())
            else:
                extra_text = str(extra)

            text_with_extra = text + "\n\n" + extra_text
        else:
            text_with_extra = text

        tags = [self.mode.lower()] + tags

        outro = f"\n{source}" f"\n#" + " #".join(tags)

        text += outro
        text_with_extra += outro

        try:
            await self.tg.send(self.bug_chat, text_with_extra, markup=None)

        # pylint: disable=broad-except
        except Exception as e:
            if extra:
                logger.error(f"{SYMBOLS[3]}  Send report  {extra} {e}")

                try:
                    await self.tg.send(self.bug_chat, text, markup=None)

                # pylint: disable=broad-except,redefined-outer-name
                except Exception as e:
                    logger.error(f"{SYMBOLS[3]}  Send report  {type_} {text} {e}")

            else:
                logger.error(f"{SYMBOLS[3]}  Send report  {type_} {text} {e}")

    @staticmethod
    async def debug(text, extra=None):
        """Debug: log to file only; never sends to Telegram."""

        logger.debug(f"{SYMBOLS[0]}  {text}  {dump(extra)}")

    async def info(self, text, extra=None, tags=None, silent=False):
        """Info: system logs/event journal; Telegram only in PRE/PROD unless silent."""

        extra = dump(extra)
        logger.info(f"{SYMBOLS[1]}  {text}  {json.dumps(extra, ensure_ascii=False)}")

        if not silent:
            await self._report(text, 1, extra, tags)

    async def warning(
        self,
        text,
        extra=None,
        tags=None,
        error=None,
        silent=False,
    ):
        """Warning: unexpected behavior; logs and sends with caller/traceback info."""

        extra = dump(extra)
        logger.warning(f"{SYMBOLS[2]}  {text}  {json.dumps(extra, ensure_ascii=False)}")

        if not silent:
            await self._report(text, 2, extra, tags, error)

    async def error(
        self,
        text,
        extra=None,
        tags=None,
        error=None,
        silent=False,
    ):
        """Error: unhandled failure; logs and sends with traceback if provided."""

        extra = dump(extra)
        content = (
            "".join(traceback.format_exception(None, error, error.__traceback__))
            if error is not None
            else f"{text}  {json.dumps(extra, ensure_ascii=False)}"
        )
        logger.error(f"{SYMBOLS[3]}  {content}")

        if not silent:
            await self._report(text, 3, extra, tags, error)

    async def critical(
        self,
        text,
        extra=None,
        tags=None,
        error=None,
        silent=False,
    ):
        """Critical: service-affecting error; logs and sends with traceback if provided."""

        extra = dump(extra)
        content = (
            "".join(traceback.format_exception(None, error, error.__traceback__))
            if error is not None
            else f"{text}  {json.dumps(extra, ensure_ascii=False)}"
        )
        logger.critical(f"{SYMBOLS[4]}  {content}")

        if not silent:
            await self._report(text, 4, extra, tags, error)

    async def important(self, text, extra=None, tags=None, silent=False):
        """Important: notable tracked user action; no traceback in message."""

        extra = dump(extra)
        logger.info(f"{SYMBOLS[5]}  {text}  {json.dumps(extra, ensure_ascii=False)}")

        if not silent:
            await self._report(text, 5, extra, tags)

    async def request(self, text, extra=None, tags=None, silent=False):
        """Request: user/Admin attention needed; no traceback in message."""

        extra = dump(extra)
        logger.info(f"{SYMBOLS[6]}  {text}  {json.dumps(extra, ensure_ascii=False)}")

        if not silent:
            await self._report(text, 6, extra, tags)
