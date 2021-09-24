"""
Reports functionality
"""

import json
import inspect
import traceback
import logging
import logging.config
from pathlib import Path

from tgio import Telegram


SYMBOLS = ['💬', '🟢', '🟡', '🔴', '❗️', '✅', '🛎']
TYPES = [
    'DEBUG', 'INFO',
    'WARNING', 'ERROR', 'CRITICAL',
    'IMPORTANT', 'REQUEST',
]


log_file = Path(__file__).parent / 'log.conf'
logging.config.fileConfig(log_file)
logger_err = logging.getLogger(__name__)
logger_log = logging.getLogger('info')


def to_json(data):
    """ Convert any type to json serializable object """

    if isinstance(data, str):
        return data

    try:
        return json.dumps(data)
    except TypeError:
        return str(data)

def dump(data):
    """ json.dumps() with errors handler """

    if data is None:
        return None

    if not isinstance(data, dict):
        return str(data)

    return {
        k: to_json(v)
        for k, v in data.items()
        if v is not None
    }


class Report():
    """ Report logs and notifications on Telegram chat or in log files """

    def __init__(self, mode, token, bug_chat):
        self.mode = mode
        self.tg = Telegram(token)
        self.bug_chat = bug_chat

    async def _report(self, text, type_=0, extra=None, tags=None):
        """ Make report message and send """

        if self.mode not in ('PRE', 'PROD') and type_ == 0:
            return

        if not tags:
            tags = []

        previous = inspect.stack()[2]
        path = previous.filename.replace('/', '.').split('.')[2:-1]

        if path[0] == 'api':
            path = path[1:]

        if previous.function != 'handle':
            path.append(previous.function)

        path = '.'.join(path)

        text = f"{SYMBOLS[type_]} {self.mode} {TYPES[type_]}" \
               f"\n{path}" \
               f"\n\n{text}"

        if extra:
            print('###', extra)
            if isinstance(extra, dict):
                extra_text = "\n".join(
                    f"{k} = {v}"
                    for k, v in extra.items()
                )
            else:
                extra_text = str(extra)

            text_with_extra = text + "\n\n" + extra_text
        else:
            text_with_extra = text

        tags = [self.mode.lower()] + tags
        outro = f"\n\n{previous.filename}:{previous.lineno}" \
                f"\n#" + " #".join(tags)

        text += outro
        text_with_extra += outro

        try:
            await self.tg.send(self.bug_chat, text_with_extra, markup=None)

        # pylint: disable=broad-except
        except Exception as e:
            if extra:
                logger_err.error(
                    "%s  Send report  %s %s",
                    SYMBOLS[3], extra, e,
                )

                try:
                    await self.tg.send(self.bug_chat, text, markup=None)

                # pylint: disable=broad-except
                except Exception as e:
                    logger_err.error(
                        "%s  Send report  %s %s %s",
                        SYMBOLS[3], type_, text, e,
                    )

            else:
                logger_err.error(
                    "%s  Send report  %s %s %s",
                    SYMBOLS[3], type_, text, e,
                )


    @staticmethod
    async def debug(text, extra=None):
        """ Debug
        Sequence of function calls, internal values
        """

        logger_log.debug("%s  %s  %s", SYMBOLS[0], text, dump(extra))

    async def info(self, text, extra=None, tags=None):
        """ Info
        System logs and event journal
        """

        extra = dump(extra)
        logger_log.info("%s  %s  %s", SYMBOLS[1], text, json.dumps(extra))
        await self._report(text, 1, extra, tags)

    async def warning(self, text, extra=None, tags=None):
        """ Warning
        Unexpected / strange code behavior that does not entail consequences
        """

        extra = dump(extra)
        logger_err.warning("%s  %s  %s", SYMBOLS[2], text, json.dumps(extra))
        await self._report(text, 2, extra, tags)

    async def error(self, text, extra=None, tags=None, error=None):
        """ Error
        An unhandled error occurred
        """

        extra = dump(extra)
        content = (
            "".join(
                traceback.format_exception(None, error, error.__traceback__)
            )
            if error is not None else
            f"{text}  {json.dumps(extra)}"
        )

        logger_err.error("%s  %s", SYMBOLS[3], content)
        await self._report(text, 3, extra, tags)

    async def critical(self, text, extra=None, tags=None, error=None):
        """ Critical
        An error occurred that affects the operation of the service
        """

        extra = dump(extra)
        content = (
            "".join(
                traceback.format_exception(None, error, error.__traceback__)
            )
            if error is not None else
            f"{text}  {json.dumps(extra)}"
        )

        logger_err.critical("%s  %s", SYMBOLS[4], content)
        await self._report(text, 4, extra, tags)

    async def important(self, text, extra=None, tags=None):
        """ Important
        Trigger on tracked user action was fired
        """

        extra = dump(extra)
        logger_log.info("%s  %s  %s", SYMBOLS[5], text, json.dumps(extra))
        await self._report(text, 5, extra, tags)

    async def request(self, text, extra=None, tags=None):
        """ Request
        The user made a request, the intervention of administrators is necessary
        """

        extra = dump(extra)
        logger_log.info("%s  %s  %s", SYMBOLS[6], text, json.dumps(extra))
        await self._report(text, 6, extra, tags)
