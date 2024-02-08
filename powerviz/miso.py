"""
TODO:
    - parse future forecasts
    - multiprocess parsing pipeline (realtime lmp very slow)
    - manager worker scheme for fetching/parsing (see BaseClient)
"""

import asyncio
import datetime as dt
import enum
import io
import json
import warnings
from typing import Callable, Literal, Optional
from zipfile import ZipFile

import aiohttp
import pandas as pd
import pytz
import tqdm
from tqdm.asyncio import tqdm_asyncio

from powerviz.base import BaseClient
from powerviz.types import Dates, DatesTypeError


class MISOMarketReport(enum.Enum):
    FORECAST_AND_LOAD = "Hourly Forecast and Actual Load"
    GENERATION_FUEL_MIX = (
        "Hourly Real-Time Generation and Day-Ahead Cleared Fuel Mix"
    )
    DAYAHEAD_EXANTE_LMP = "Hourly Day-Ahead Ex-Ante Locational Marginal Prices"
    DAYAHEAD_EXPOST_LMP = (
        "Hourly Day-Ahead Ex-Post (Extended) Locational Marginal Prices"
    )
    REALTIME_EXANTE_LMP = "5-Min Real-Time Ex-Ante Locational Marginal Prices"


class MISOClient(BaseClient):
    NAME = "MISO"
    TIMEZONE = "EST"

    HUB_NAMES = (
        "ARKANSAS.HUB",
        "ILLINOIS.HUB",
        "INDIANA.HUB",
        "LOUISIANA.HUB",
        "MICHIGAN.HUB",
        "MINN.HUB",
        "MS.HUB",
        "TEXAS.HUB",
    )

    def __init__(
        self,
        concurrent_limit: int = 25,
        session: Optional[aiohttp.ClientSession] = None,
        timeout: Optional[aiohttp.ClientTimeout] = None,
    ) -> None:
        super().__init__(
            concurrent_limit=concurrent_limit, session=session, timeout=timeout
        )

    async def get_load_data(self, dates: Dates) -> pd.DataFrame:
        """
        Real-time load data is given in 5-min intervals from API.
        Historical data is hourly intervals from market report files.
        """

        load_df: pd.DataFrame
        if dates in ("latest", "today"):
            url = (
                "https://api.misoenergy.org/MISORTWDDataBroker/DataBroker"
                "Services.asmx?messageType=gettotalload&returnType=json"
            )

            resp: aiohttp.ClientResponse = await self._fetch(url)
            json_data: bytes
            async with resp:
                json_data = await resp.read()

            load_df = self.parse_load_api_data(json_data)
            if dates == "latest":
                load_df = load_df.iloc[-1:].reset_index(drop=True)

        elif isinstance(dates, list) and all(
            isinstance(date, dt.datetime) for date in dates
        ):
            load_df = await self.retrieve_and_parse_market_report_files(
                dates,
                MISOMarketReport.FORECAST_AND_LOAD,
                self.parse_forecast_and_load_market_report,
            )

            # exclude forecast col
            load_df = load_df[["start", "end", "load"]]

        else:
            raise DatesTypeError()

        return load_df

    def parse_load_api_data(self, json_data: bytes) -> pd.DataFrame:
        load_json = json.load(io.BytesIO(json_data))

        refid_str = load_json["LoadInfo"]["RefId"]
        date = self.parse_api_refid_datetime(refid_str).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        load_data: list[dict[str, dt.datetime | float]] = []
        for load_dict in load_json["LoadInfo"]["FiveMinTotalLoad"]:
            time: str = load_dict["Load"]["Time"]  # {hour}:{minute}
            load: int = load_dict["Load"]["Value"]
            hour, minute = (int(t) for t in time.split(":", maxsplit=1))

            start = date.replace(hour=hour, minute=minute)
            end = start + dt.timedelta(minutes=5)

            load_data.append(
                {
                    "start": start,
                    "end": end,
                    "load": round(float(load), 2),
                }
            )

        load_df = pd.DataFrame(load_data).sort_values(
            by="start", ascending=True, ignore_index=True
        )
        return load_df

    def parse_forecast_and_load_market_report(
        self, xls_data: bytes
    ) -> pd.DataFrame:
        forecast_load_df = pd.read_excel(
            io.BytesIO(xls_data),
            skiprows=[0, 1, 2, 3, 5],  # skip date and title
            nrows=24,  # only read current day (skip future forecasts)
            engine="calamine",  # type: ignore [call-overload]
        )

        use_cols = [
            "Market Day",
            "HourEnding",
            "MISO MTLF (MWh)",
            "MISO ActualLoad (MWh)",
        ]
        new_cols = [
            "start",
            "end",
            "forecast",
            "load",
        ]

        forecast_load_df = forecast_load_df[use_cols].rename(
            columns=dict(zip(use_cols, new_cols))
        )

        forecast_load_df["start"] = (
            pd.to_datetime(forecast_load_df["start"])
            + pd.to_timedelta(forecast_load_df["end"] - 1, unit="hours")
        ).apply(self.to_native_tz)
        forecast_load_df["end"] = forecast_load_df["start"] + dt.timedelta(
            hours=1
        )
        forecast_load_df["forecast"] = (
            forecast_load_df["forecast"].astype(float).round(2)
        )
        forecast_load_df["load"] = (
            forecast_load_df["load"].astype(float).round(2)
        )

        forecast_load_df = forecast_load_df.sort_values(
            by="start", ascending=True, ignore_index=True
        )

        return forecast_load_df

    async def get_forecast_data(self, dates: Dates) -> pd.DataFrame:
        """
        Real-time forecast data is given in hourly intervals from API.
        Historical data is hourly intervals from market report files.
        """

        forecast_df: pd.DataFrame
        if dates in ("latest", "today"):
            url = (
                "https://api.misoenergy.org/MISORTWDDataBroker/DataBroker"
                "Services.asmx?messageType=gettotalload&returnType=json"
            )

            resp: aiohttp.ClientResponse = await self._fetch(url)
            json_data: bytes
            async with resp:
                json_data = await resp.read()

            forecast_df = self.parse_forecast_api_data(json_data)
            if dates == "latest":
                current_hour = dt.datetime.now(
                    pytz.timezone(self.TIMEZONE)
                ).replace(minute=0, second=0, microsecond=0)
                forecast_df = forecast_df[
                    forecast_df["start"] == current_hour
                ].reset_index(drop=True)

        elif isinstance(dates, list) and all(
            isinstance(date, dt.datetime) for date in dates
        ):
            forecast_df = await self.retrieve_and_parse_market_report_files(
                dates,
                MISOMarketReport.FORECAST_AND_LOAD,
                self.parse_forecast_and_load_market_report,
            )

            # exclude load col
            forecast_df = forecast_df[["start", "end", "forecast"]]

        else:
            raise DatesTypeError()

        return forecast_df

    def parse_forecast_api_data(self, json_data: bytes) -> pd.DataFrame:
        forecast_json = json.load(io.BytesIO(json_data))

        refid_str = forecast_json["LoadInfo"]["RefId"]
        date = self.parse_api_refid_datetime(refid_str).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        forecast_data: list[dict[str, dt.datetime | float]] = []
        for forecast_dict in forecast_json["LoadInfo"][
            "MediumTermLoadForecast"
        ]:
            hour: int = int(forecast_dict["Forecast"]["HourEnding"]) - 1
            forecast: int = forecast_dict["Forecast"]["LoadForecast"]
            start = date.replace(hour=hour)
            end = start + dt.timedelta(hours=1)

            forecast_data.append(
                {
                    "start": start,
                    "end": end,
                    "forecast": round(float(forecast), 2),
                }
            )

        forecast_df = pd.DataFrame(forecast_data).sort_values(
            by="start", ascending=True, ignore_index=True
        )
        return forecast_df

    async def get_fuel_mix_data(self, dates: Dates) -> pd.DataFrame:
        """
        Real-time fuel mix data is given in 5-min intervals from API.
        Historical data is hourly intervals from market report files.
        """

        # all data for current day is not available from API
        if dates == "today":
            raise NotImplementedError(
                'Only "latest" and historical data available.'
            )

        fuel_mix_df: pd.DataFrame
        if dates == "latest":
            url = (
                "https://api.misoenergy.org/MISORTWDDataBroker/DataBroker"
                "Services.asmx?messageType=getfuelmix&returnType=json"
            )

            resp: aiohttp.ClientResponse = await self._fetch(url)
            json_data: bytes
            async with resp:
                json_data = await resp.read()

            fuel_mix_df = self.parse_fuel_mix_api_data(json_data)

        elif isinstance(dates, list) and all(
            isinstance(date, dt.datetime) for date in dates
        ):
            fuel_mix_df = await self.retrieve_and_parse_market_report_files(
                dates,
                MISOMarketReport.GENERATION_FUEL_MIX,
                self.parse_generation_fuel_mix_market_report,
            )

        else:
            raise DatesTypeError()

        return fuel_mix_df

    def parse_fuel_mix_api_data(self, json_data: bytes) -> pd.DataFrame:
        fuel_mix_json = json.load(io.BytesIO(json_data))

        refid_str = fuel_mix_json["RefId"]
        start = self.parse_api_refid_datetime(refid_str)
        end = start + dt.timedelta(minutes=5)

        fuel_mix_data: dict[str, dt.datetime | float] = {}
        fuel_mix_data["start"] = start
        fuel_mix_data["end"] = end

        for fuel_dict in fuel_mix_json["Fuel"]["Type"]:
            datetime_str: str = fuel_dict["INTERVALEST"]
            fuel_type: str = fuel_dict["CATEGORY"]
            fuel_mw_str: str = fuel_dict["ACT"]

            datetime = self.to_native_tz(
                dt.datetime.strptime(datetime_str, "%Y-%m-%d %I:%M:%S %p")
            )
            assert datetime == start
            fuel_type = fuel_type.lower().replace(" ", "_")
            fuel_mw = round(float(fuel_mw_str), 2)

            fuel_mix_data[fuel_type] = fuel_mw

        fuel_mix_data["total"] = round(float(fuel_mix_json["TotalMW"]), 2)

        fuel_mix_df = pd.DataFrame([fuel_mix_data])
        return fuel_mix_df

    def parse_generation_fuel_mix_market_report(
        self, xlsx_data: bytes
    ) -> pd.DataFrame:
        fuel_mix_df = pd.read_excel(
            io.BytesIO(xlsx_data),
            sheet_name="RT Generation Fuel Mix",
            nrows=28,  # include date and title for parsing date
            engine="calamine",  # type: ignore [call-overload]
        )

        date = self.to_native_tz(
            dt.datetime.strptime(
                fuel_mix_df.iloc[1, 0], "Market Date: %Y-%m-%d"
            ).replace(hour=0, minute=0, second=0, microsecond=0)
        )

        header_row = 3
        fuel_mix_df.columns = fuel_mix_df.iloc[header_row].values

        # skip regional data (only keep whole miso data)
        # miso data start at "HE" (hour ending) col
        miso_start_col = fuel_mix_df.columns.get_loc("HE")
        fuel_mix_df = fuel_mix_df.iloc[header_row + 1 :, miso_start_col:]

        new_cols = {
            "HE": "start",
            "Gas": "natural_gas",
            "MISO": "total",
        }
        new_cols |= {
            col: col.lower()
            for col in fuel_mix_df.columns
            if col not in new_cols
        }
        fuel_mix_df = fuel_mix_df.rename(columns=new_cols)

        fuel_mix_df["start"] = date + pd.to_timedelta(
            fuel_mix_df["start"] - 1, unit="hour"
        )
        fuel_mix_df["end"] = fuel_mix_df["start"] + dt.timedelta(hours=1)
        for col in fuel_mix_df.columns:
            if col not in ("start", "end"):
                fuel_mix_df[col] = fuel_mix_df[col].astype(float).round(2)

        sort_cols = (
            ["start", "end"]
            + [
                col
                for col in fuel_mix_df.columns
                if col not in ("start", "end", "other", "total")
            ]
            + ["other", "total"]
        )
        fuel_mix_df = fuel_mix_df[sort_cols].sort_values(
            by="start", ascending=True, ignore_index=True
        )
        return fuel_mix_df

    async def get_realtime_lmp_data(self, dates: Dates) -> pd.DataFrame:
        """
        Real-time LMP data is given in 5-min intervals from API.
        Data for current day will use "Ex-Post" price.
        Historical data is 5-min intervals from market report files.
        Historical data will use "Ex-Ante" price.

        MISO's new pricing method Extended LMP (ELMP) is called
        "Ex-Post". Original method is called "Ex-Ante".
        """

        lmp_df: pd.DataFrame
        if dates in ("latest", "today"):
            interval: str
            if dates == "latest":
                interval = "currentinterval"
            elif dates == "today":
                interval = "rollingmarketday"
            url = (
                "https://api.misoenergy.org/MISORTWDBIReporter/"
                f"Reporter.asmx?messageType={interval}&returnType=csv"
            )

            resp: aiohttp.ClientResponse = await self._fetch(url)
            csv_data: bytes
            async with resp:
                csv_data = await resp.read()

            lmp_df = self.parse_realtime_expost_lmp_api_data(csv_data)

        elif isinstance(dates, list) and all(
            isinstance(date, dt.datetime) for date in dates
        ):
            lmp_df = await self.retrieve_and_parse_market_report_files(
                dates,
                MISOMarketReport.REALTIME_EXANTE_LMP,
                self.parse_realtime_exante_lmp_market_report,
            )

        else:
            raise DatesTypeError()

        return lmp_df

    def parse_realtime_expost_lmp_api_data(
        self, csv_data: bytes
    ) -> pd.DataFrame:
        lmp_df = pd.read_csv(io.BytesIO(csv_data))

        use_cols = [
            "INTERVAL",
            "CPNODE",
            "LMP",
            "MLC",
            "MCC",
        ]
        new_cols = [
            "start",
            "node",
            "lmp",
            "mlc",
            "mcc",
        ]
        lmp_df = lmp_df[use_cols].rename(columns=dict(zip(use_cols, new_cols)))

        lmp_df = lmp_df[lmp_df["node"].isin(self.HUB_NAMES)]

        lmp_df["start"] = pd.to_datetime(lmp_df["start"]).apply(
            self.to_native_tz
        )
        lmp_df["node"] = lmp_df["node"].astype(pd.CategoricalDtype())
        lmp_df["lmp"] = lmp_df["lmp"].astype(float).round(2)
        lmp_df["mlc"] = lmp_df["mlc"].astype(float).round(2)
        lmp_df["mcc"] = lmp_df["mcc"].astype(float).round(2)
        lmp_df["end"] = lmp_df["start"] + dt.timedelta(minutes=5)

        cols_order = [
            "start",
            "end",
            "node",
            "lmp",
            "mlc",
            "mcc",
        ]
        lmp_df = lmp_df[cols_order].sort_values(
            by=["start", "node"], ascending=True, ignore_index=True
        )
        return lmp_df

    def parse_realtime_exante_lmp_market_report(
        self, xlsx_data: bytes
    ) -> pd.DataFrame:
        lmp_df = pd.read_excel(
            io.BytesIO(xlsx_data),
            skiprows=3,  # skip date and description
            skipfooter=1,  # skip warning
            engine="calamine",  # type: ignore [call-overload]
        )

        use_cols = [
            "Time (EST)",
            "CP Node",
            "RT Ex-Ante LMP",
            "RT Ex-Ante MLC",
            "RT Ex-Ante MCC",
        ]
        new_cols = [
            "start",
            "node",
            "lmp",
            "mlc",
            "mcc",
        ]
        lmp_df = lmp_df[use_cols].rename(columns=dict(zip(use_cols, new_cols)))

        lmp_df = lmp_df[lmp_df["node"].isin(self.HUB_NAMES)]

        lmp_df["start"] = pd.to_datetime(lmp_df["start"]).apply(
            self.to_native_tz
        )
        lmp_df["node"] = lmp_df["node"].astype(pd.CategoricalDtype())
        lmp_df["lmp"] = lmp_df["lmp"].astype(float).round(2)
        lmp_df["mlc"] = lmp_df["mlc"].astype(float).round(2)
        lmp_df["mcc"] = lmp_df["mcc"].astype(float).round(2)
        lmp_df["end"] = lmp_df["start"] + dt.timedelta(minutes=5)

        cols_order = [
            "start",
            "end",
            "node",
            "lmp",
            "mlc",
            "mcc",
        ]
        lmp_df = lmp_df[cols_order].sort_values(
            by=["start", "node"], ascending=True, ignore_index=True
        )
        return lmp_df

    async def get_dayahead_lmp_data(
        self,
        dates: Dates,
        price_type: Literal[
            MISOMarketReport.DAYAHEAD_EXANTE_LMP,
            MISOMarketReport.DAYAHEAD_EXPOST_LMP,
        ] = MISOMarketReport.DAYAHEAD_EXPOST_LMP,
    ) -> pd.DataFrame:
        """
        Day-ahead LMP data is given in hourly intervals.
        All data is from market report files.

        Defaults to MISO's new pricing method -- Extended LMP (ELMP),
        which they call Ex-Post. Original method is called Ex-Ante.
        """

        lmp_df: pd.DataFrame
        if dates in ("latest", "today"):
            lmp_df = await self.retrieve_and_parse_market_report_files(
                [dt.datetime.now(pytz.timezone(self.TIMEZONE))],
                price_type,
                self.parse_dayahead_lmp_market_report,
            )

            if dates == "latest":
                current_hour = dt.datetime.now(
                    pytz.timezone(self.TIMEZONE)
                ).replace(minute=0, second=0, microsecond=0)
                lmp_df = lmp_df[lmp_df["start"] == current_hour].reset_index(
                    drop=True
                )

        elif isinstance(dates, list) and all(
            isinstance(date, dt.datetime) for date in dates
        ):
            lmp_df = await self.retrieve_and_parse_market_report_files(
                dates, price_type, self.parse_dayahead_lmp_market_report
            )

        else:
            raise DatesTypeError()

        return lmp_df

    def parse_dayahead_lmp_market_report(
        self, csv_data: bytes
    ) -> pd.DataFrame:
        io_csv_data = io.BytesIO(csv_data)

        _ = io_csv_data.readline()
        date_str = io_csv_data.readline().decode().strip("\n\r ")
        date = self.to_native_tz(
            dt.datetime.strptime(date_str, "%m/%d/%Y").replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        )

        io_csv_data.seek(0)
        lmp_df = pd.read_csv(
            io_csv_data,
            skiprows=4,  # skip date and description
        )

        use_cols = ["Node", "Value"] + [f"HE {hour}" for hour in range(1, 25)]
        lmp_df = lmp_df[use_cols]

        lmp_df = lmp_df[lmp_df["Node"].isin(self.HUB_NAMES)]

        lmp_df = (
            lmp_df.melt(
                id_vars=["Node", "Value"], var_name="Start", value_name="Price"
            )
            .pivot(index=["Start", "Node"], columns="Value", values="Price")
            .reset_index()
        )

        lmp_df.columns.name = ""

        lmp_df["Start"] = lmp_df["Start"].apply(
            lambda hour_end_str, date=date: date.replace(
                hour=int(hour_end_str.split(" ", maxsplit=1)[-1]) - 1
            )
        )
        lmp_df["End"] = lmp_df["Start"] + dt.timedelta(hours=1)
        lmp_df["Node"] = lmp_df["Node"].astype(pd.CategoricalDtype())
        for col in ("LMP", "MLC", "MCC"):
            lmp_df[col] = lmp_df[col].astype(float).round(2)

        lmp_df = lmp_df.rename(
            columns={
                "Start": "start",
                "End": "end",
                "Node": "node",
                "LMP": "lmp",
                "MCC": "mcc",
                "MLC": "mlc",
            }
        )

        lmp_df = lmp_df[
            ["start", "end", "node", "lmp", "mlc", "mcc"]
        ].sort_values(by=["start", "node"], ascending=True, ignore_index=True)
        return lmp_df

    async def retrieve_and_parse_market_report_files(
        self,
        dates: list[dt.datetime],
        report: MISOMarketReport,
        parse_fn: Callable[[bytes], pd.DataFrame],
    ) -> pd.DataFrame:

        dates = [self.to_native_tz(date) for date in dates]
        urls_dict: dict[dt.datetime, str] = (
            await self.get_all_market_report_urls(dates, report)
        )

        # set of all expected market report file names
        # non-archived market report file names included as is.
        # names of archived market report files are included as
        # if they are unarchived/unzipped.
        # this is done to avoided parsing un-requested files
        # which are also present inside the archive/zip file
        # e.g. this happens when requesting a partial month
        # of archived data
        # will remove file names from set as they are retrieved
        # and warn user of any unretrieved files at end
        unretrieved_files = {
            self.market_report_filename(date, report, is_archived=False)
            for date in urls_dict.keys()
        }

        dfs: list[pd.DataFrame] = []
        urls = set(urls_dict.values())
        with tqdm.tqdm(
            total=len(unretrieved_files),
            desc="Retrieving/Parsing market report files",
        ) as progress_bar:
            for coro in asyncio.as_completed(
                [self._fetch(url) for url in urls]
            ):
                resp: aiohttp.ClientResponse = await coro
                filename = str(resp.url).rsplit("/", maxsplit=1)[-1]
                ext = filename.rsplit(".", maxsplit=1)[-1]

                file_data: bytes
                async with resp:
                    file_data = await resp.read()

                if ext == "zip":
                    with ZipFile(io.BytesIO(file_data), mode="r") as zfile:
                        for file in zfile.filelist:
                            filename = file.filename
                            if filename in unretrieved_files:
                                file_data = zfile.read(filename)

                                dfs.append(parse_fn(file_data))
                                unretrieved_files.remove(filename)
                                progress_bar.update(1)

                else:
                    assert filename in unretrieved_files

                    dfs.append(parse_fn(file_data))
                    unretrieved_files.remove(filename)
                    progress_bar.update(1)

        if len(unretrieved_files) > 0:
            warnings.warn(
                (
                    "Not all market report files retrieved. "
                    f"Missing:\n{list(unretrieved_files)}"
                )
            )

        # combine all dataframes and sort
        # sorting rows by order of columns
        # i.e. expecting "Start"/"End" (date) columns to be first
        df = pd.concat(dfs)
        df = df.sort_values(
            by=df.columns.tolist(), ascending=True, ignore_index=True
        )
        return df

    async def get_all_market_report_urls(
        self,
        dates: list[dt.datetime],
        report: MISOMarketReport,
    ) -> dict[dt.datetime, str]:
        dates = [self.to_native_tz(date) for date in dates]
        urls = await tqdm_asyncio.gather(
            *[self.market_report_url(d, report) for d in dates],
            desc="Retrieving market report file urls",
        )
        urls_dict = {
            date: url for date, url in zip(dates, urls) if url is not None
        }

        missing_dates = [
            date.isoformat() for date, url in zip(dates, urls) if url is None
        ]
        if len(missing_dates) > 0:
            warnings.warn(
                (
                    "Not all requested data is available. "
                    f"The following dates are missing:\n{missing_dates}"
                )
            )

        return urls_dict

    async def market_report_url(
        self, date: dt.datetime, report: MISOMarketReport
    ) -> str | None:
        """
        Market report files are published daily and contain data
        from the previous market day.
        After some time (a few years), market report files are archived.
        Archived files are zip files containing the daily files
        for the whole month.

        This method will return the url to the file containing data
        for the provided date (i.e. check if report file is archived
        or not, then return a url to the corresponding report file).
        If neither file exists, return None.
        """

        BASE_URL = (  # pylint: disable=invalid-name
            "https://docs.misoenergy.org/marketreports"
        )

        date = self.to_native_tz(date)

        # check if non-archived url exists
        non_archived_url = self.urljoin(
            BASE_URL,
            self.market_report_filename(date, report, is_archived=False),
        )
        # return non-archived url if exists
        if await self.check_url_exists(non_archived_url):
            return non_archived_url

        # check if archived url exists
        archived_url = self.urljoin(
            BASE_URL,
            self.market_report_filename(date, report, is_archived=True),
        )
        # return archived url if exists
        if await self.check_url_exists(archived_url):
            return archived_url

        # if neither url exists, return None
        return None

    def market_report_filename(
        self,
        date: dt.datetime,
        report: MISOMarketReport,
        is_archived: bool,
    ) -> str:

        MARKET_REPORT_FILES_SUFFIX_EXT = {  # pylint: disable=invalid-name
            MISOMarketReport.FORECAST_AND_LOAD: ("df_al", "xls"),
            MISOMarketReport.GENERATION_FUEL_MIX: ("sr_gfm", "xlsx"),
            MISOMarketReport.DAYAHEAD_EXANTE_LMP: ("da_exante_lmp", "csv"),
            MISOMarketReport.DAYAHEAD_EXPOST_LMP: ("da_expost_lmp", "csv"),
            MISOMarketReport.REALTIME_EXANTE_LMP: ("5min_exante_lmp", "xlsx"),
        }

        date = self.to_native_tz(date)

        # some report files are named using publish date
        # instead of market date (publish date is day after market date)
        if report in (
            MISOMarketReport.FORECAST_AND_LOAD,
            MISOMarketReport.GENERATION_FUEL_MIX,
            MISOMarketReport.REALTIME_EXANTE_LMP,
        ):
            date = date + dt.timedelta(days=1)

        date_fmt: str
        suffix, ext = MARKET_REPORT_FILES_SUFFIX_EXT[report]
        if is_archived:
            suffix = suffix + "_" + ext
            ext = "zip"
            date_fmt = "%Y%m"
        else:
            date_fmt = "%Y%m%d"

        return f"{date.strftime(date_fmt)}_{suffix}.{ext}"

    def parse_api_refid_datetime(self, refid_str: str) -> dt.datetime:
        # refid_str: '{day}-{month}-{year} - Interval {hour}:{min} EST'
        refid_split = refid_str.split()

        if refid_split[-1] != "EST" or refid_split[1:3] != ["-", "Interval"]:
            raise ValueError("Invalid refid string.")

        # exclude tz string when parsing (can't parse "EST")
        datetime = dt.datetime.strptime(
            refid_str[:-4], "%d-%b-%Y - Interval %H:%M"
        )

        # add back timezone
        datetime = self.to_native_tz(datetime)

        return datetime
