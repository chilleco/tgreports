"""Telegram reporting helpers: logs to files and sends Telegram notifications.

- Loads a `log.conf` from the CWD if present, otherwise falls back to the packaged
  config.
- Provides async helpers that both write to log files and push formatted messages
  to a Telegram chat using `tgio.Telegram`.
"""

import json
import inspect
import traceback
import logging
import logging.config
from os.path import exists
from pathlib import Path

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


# pylint: disable=invalid-name
if exists("log.conf"):
    log_file = "log.conf"
else:
    log_file = Path(__file__).parent / "log.conf"
logging.config.fileConfig(log_file)
logger_err = logging.getLogger(__name__)
logger_log = logging.getLogger("info")


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

    def __init__(self, mode, token, bug_chat):
        """Initialize a reporter.

        Args:
            mode: Environment label (e.g., LOCAL/TEST/DEV/PRE/PROD) used in
                messages and to gate info-level Telegram sends (only PRE/PROD).
            token: Telegram bot token.
            bug_chat: Target chat/channel id for notifications.
        """
        self.mode = mode or "TEST"
        self.tg = Telegram(token)
        self.bug_chat = bug_chat

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
                logger_err.error(
                    "%s  Send report  %s %s",
                    SYMBOLS[3],
                    extra,
                    e,
                )

                try:
                    await self.tg.send(self.bug_chat, text, markup=None)

                # pylint: disable=broad-except,redefined-outer-name
                except Exception as e:
                    logger_err.error(
                        "%s  Send report  %s %s %s",
                        SYMBOLS[3],
                        type_,
                        text,
                        e,
                    )

            else:
                logger_err.error(
                    "%s  Send report  %s %s %s",
                    SYMBOLS[3],
                    type_,
                    text,
                    e,
                )

    @staticmethod
    async def debug(text, extra=None):
        """Debug: log to file only; never sends to Telegram."""

        logger_log.debug("%s  %s  %s", SYMBOLS[0], text, dump(extra))

    async def info(self, text, extra=None, tags=None, silent=False):
        """Info: system logs/event journal; Telegram only in PRE/PROD unless silent."""

        extra = dump(extra)
        logger_log.info(
            "%s  %s  %s",
            SYMBOLS[1],
            text,
            json.dumps(extra, ensure_ascii=False),
        )

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
        logger_err.warning(
            "%s  %s  %s",
            SYMBOLS[2],
            text,
            json.dumps(extra, ensure_ascii=False),
        )

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
        logger_err.error("%s  %s", SYMBOLS[3], content)

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
        logger_err.critical("%s  %s", SYMBOLS[4], content)

        if not silent:
            await self._report(text, 4, extra, tags, error)

    async def important(self, text, extra=None, tags=None, silent=False):
        """Important: notable tracked user action; no traceback in message."""

        extra = dump(extra)
        logger_log.info(
            "%s  %s  %s",
            SYMBOLS[5],
            text,
            json.dumps(extra, ensure_ascii=False),
        )

        if not silent:
            await self._report(text, 5, extra, tags)

    async def request(self, text, extra=None, tags=None, silent=False):
        """Request: user/Admin attention needed; no traceback in message."""

        extra = dump(extra)
        logger_log.info(
            "%s  %s  %s",
            SYMBOLS[6],
            text,
            json.dumps(extra, ensure_ascii=False),
        )

        if not silent:
            await self._report(text, 6, extra, tags)
