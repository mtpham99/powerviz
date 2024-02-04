import asyncio
import datetime as dt
import os
from typing import Literal

import pandas as pd
import pytz

from powerviz.miso import MISOClient


def save_df_csv(df: pd.DataFrame, save_path: str, save_name: str) -> None:
    os.makedirs(save_path, exist_ok=True)
    df.to_csv(os.path.join(save_path, save_name), index=False)


async def main() -> None:
    # Data client
    miso_client = MISOClient(concurrent_limit=25)

    # Data range
    # 2020 Dec 28 - 2021 Jan 4
    # Example range chosen b/c at time of writing
    # 2020 data is archived while 2021 data is NOT archived
    timezone = pytz.timezone("EST")
    start = timezone.localize(dt.datetime(2020, 12, 28, 0, 0, 0))
    end = timezone.localize(dt.datetime(2021, 1, 4, 0, 0, 0))
    dates_list = (
        pd.date_range(start, end, freq="D")  # pylint: disable=no-member
        .to_pydatetime()
        .tolist()
    )

    save_dir = os.path.join(os.getcwd(), "data", "miso")
    for interval in ("latest", "today", "history"):

        dates: Literal["latest", "today"] | list[dt.datetime]
        if interval in ("latest", "today"):
            dates = interval  # type: ignore
        elif interval == "history":
            dates = dates_list

        # Load Data
        print(f"Getting Load Data ({interval})")
        df = await miso_client.get_load_data(dates=dates)
        save_df_csv(
            df=df,
            save_path=os.path.join(save_dir, "load"),
            save_name=f"{interval}.csv",
        )

        # Forecast Data
        print(f"Getting Forecast Data ({interval})")
        df = await miso_client.get_forecast_data(dates=dates)
        save_df_csv(
            df=df,
            save_path=os.path.join(save_dir, "forecast"),
            save_name=f"{interval}.csv",
        )

        # Fuel Mix Data
        if interval == "today":
            print('"today" data not available for "fuel mix". Skipping.')
        else:
            print(f"Getting Fuel Mix Data ({interval})")
            df = await miso_client.get_fuel_mix_data(dates=dates)
            save_df_csv(
                df=df,
                save_path=os.path.join(save_dir, "fuel_mix"),
                save_name=f"{interval}.csv",
            )

        # Real-Time LMP Data
        print(f"Getting Real-Time LMP Data ({interval})")
        df = await miso_client.get_realtime_lmp_data(dates=dates)
        save_df_csv(
            df=df,
            save_path=os.path.join(save_dir, "real_time_lmp"),
            save_name=f"{interval}.csv",
        )

        # Day-Ahead LMP Data
        print(f"Getting Day-Ahead LMP Data ({interval})")
        df = await miso_client.get_dayahead_lmp_data(dates=dates)
        save_df_csv(
            df=df,
            save_path=os.path.join(save_dir, "day_ahead_lmp"),
            save_name=f"{interval}.csv",
        )

        print("\n")


if __name__ == "__main__":
    asyncio.run(main())
