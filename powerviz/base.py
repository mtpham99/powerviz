import abc
import asyncio
import atexit
import datetime as dt
from typing import Optional, TypeAlias

import aiohttp
import pytz
import tenacity

RequestParams: TypeAlias = dict[str, int | str | list[str]]


def is_retryable_error(error: BaseException) -> bool:
    # TODO : retry errors
    # aiohttp.ClientResponseError: 429, message='Too Many Requests'
    # aiohttp.ClientResponseError: 404, message='Not Found'
    # don't retry 404 not found
    if isinstance(error, aiohttp.ClientResponseError):
        if error.status == 404:
            return False
    retryable_errors = [aiohttp.ClientConnectionError]
    for re_error in retryable_errors:
        if isinstance(error, re_error):
            return True
    return False


class BaseClient(abc.ABC):
    NAME: str = ""
    TIMEZONE: str = ""

    def __init__(
        self,
        concurrent_limit: int = 100,
        session: Optional[aiohttp.ClientSession] = None,
        timeout: Optional[aiohttp.ClientTimeout] = None,
    ) -> None:
        if self.NAME == "":
            raise NotImplementedError('"NAME" attribute must be defined.')
        if self.TIMEZONE == "":
            raise NotImplementedError('"TIMEZONE" attribute must be defined.')
        if self.TIMEZONE not in pytz.all_timezones_set:
            raise ValueError('"{self.TIMEZONE}" is not a valid timezone.')

        self.session = (
            session
            if session is not None
            else aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=None),
                connector=aiohttp.TCPConnector(
                    limit=None  # type: ignore [arg-type]
                ),
            )
        )

        # semaphore for limiting connections
        self.semaphore = asyncio.BoundedSemaphore(concurrent_limit)

        # make sure client is closed at exit
        atexit.register(asyncio.run, self.session.close())

        # timeout limits for every individial data get request
        self.timeout = (
            timeout
            if timeout is not None
            else aiohttp.ClientTimeout(total=None)
        )

    @tenacity.retry(
        reraise=True,
        wait=tenacity.wait_fixed(wait=10),
        stop=tenacity.stop_after_attempt(max_attempt_number=10),
        retry=tenacity.retry_if_exception(is_retryable_error),
    )
    async def _fetch(
        self,
        url: str,
        params: Optional[RequestParams] = None,
    ) -> aiohttp.ClientResponse:
        resp: aiohttp.ClientResponse
        async with self.semaphore:
            resp = await self.session.get(
                url, raise_for_status=True, params=params, timeout=self.timeout
            )
        return resp

    async def check_url_exists(self, url: str) -> bool:
        try:
            resp = await self._fetch(url)
        except aiohttp.ClientResponseError as err:
            if err.status == 404:
                return False
            raise err

        resp.close()
        return True

    @classmethod
    def to_native_tz(cls, date_time: dt.datetime) -> dt.datetime:
        # if timezone aware, convert
        if (
            date_time.tzinfo is not None
            and date_time.tzinfo.utcoffset(date_time) is not None
        ):
            return date_time.astimezone(pytz.timezone(cls.TIMEZONE))

        # timezone unaware, assume localized and explicitly add timezone
        return pytz.timezone(cls.TIMEZONE).localize(date_time)

    @classmethod
    def is_today(cls, datetime: dt.datetime) -> bool:
        date = cls.to_native_tz(datetime).date()

        tz = pytz.timezone(cls.TIMEZONE)
        today = dt.datetime.now(tz).date()

        return date == today

    @staticmethod
    def urljoin(*args: str) -> str:
        return "/".join(map(lambda x: x.strip("/"), args))
