import datetime as dt
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objs as go
import psycopg2
import pytz
from db_utils import get_data_from_table


def fill_missing_times(
    df: pd.DataFrame, start: dt.datetime, end: dt.datetime, delta: dt.timedelta
) -> pd.DataFrame:
    """
    Add rows missing times in [start, end, dt] and fill columns with nan
    """
    assert "start" in df.columns

    ndt = int((end - start) / delta)
    date_range = [start + i * delta for i in range(ndt)]

    df = df.set_index("start")
    df = df.reindex(date_range)

    df["start"] = df.index
    df["end"] = df["start"] + delta

    df = df.reset_index(drop=True)

    return df


def transform_df_to_intervals(
    df: pd.DataFrame, interval_col: str, dx: Any
) -> pd.DataFrame:
    """
    Add rows for "end of data interval" data points

    i.e.
    [x1, x2, x3, ..., xn] -> [x1, x1+dx, x2, x2+dx, xn, xn+dx]
    [y1, y2, y3, ..., yn] -> [y1, y1, y2, y2, y3, y3, ..., yn, yn]
    """

    n = df.index.size

    # double number of rows
    df = pd.concat([df, df])

    # [x1, x2, x3, ..., xn] -> [x1, x1+dx, x2, x2+dx, ..., xn, xn+dx]
    df[interval_col] = [
        x + d for x in df[interval_col].iloc[:n] for d in (0 * dx, dx)
    ]

    # [y1, y2, y3, ..., yn] -> [y1, y1, y2, y2, y3, y3, ..., yn, yn]
    for col in [c for c in df.columns if c != interval_col]:
        df[col] = [x for x in df[col].iloc[:n] for _ in range(2)]

    df = df.reset_index(drop=True)

    return df


def clean_data_frame(
    df: pd.DataFrame, start: dt.datetime, end: dt.datetime, delta: dt.timedelta
) -> pd.DataFrame:
    df = fill_missing_times(df, start, end, delta)
    df = transform_df_to_intervals(df, "start", delta)
    return df


def miso_load_and_forecast_plot(
    conn: psycopg2.extensions.connection,
) -> go.Figure:

    tz = pytz.timezone("EST")
    today = dt.datetime.now(tz).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    tomorrow = today + dt.timedelta(days=1)

    load_df = get_data_from_table(
        table="miso_load_api", conn=conn, start=today, end=tomorrow
    )
    load_df = clean_data_frame(
        load_df, start=today, end=tomorrow, delta=dt.timedelta(minutes=5)
    )
    load_df["start"] = load_df["start"].dt.tz_convert(tz)

    forecast_df = get_data_from_table(
        table="miso_forecast_api", conn=conn, start=today, end=tomorrow
    )
    forecast_df = clean_data_frame(
        forecast_df, start=today, end=tomorrow, delta=dt.timedelta(hours=1)
    )
    forecast_df["start"] = forecast_df["start"].dt.tz_convert(tz)

    fig = go.Figure(
        layout={
            "title": f"{today.strftime('%d %B %Y')}: MISO Load/Forecast",
            "xaxis": {"range": (today, tomorrow), "title": "Time (EST)"},
            "yaxis": {"title": "Load/Forecast (MW)"},
        }
    )

    fig.add_scatter(
        x=load_df["start"], y=load_df["load"], mode="lines", name="Load (MW)"
    )
    fig.add_scatter(
        x=forecast_df["start"],
        y=forecast_df["forecast"],
        mode="lines",
        name="Forecast (MW)",
    )

    return fig


def miso_fuel_mix_plot(conn: psycopg2.extensions.connection) -> go.Figure:

    tz = pytz.timezone("EST")
    today = dt.datetime.now(tz).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    tomorrow = today + dt.timedelta(days=1)

    fm_df = get_data_from_table(
        table="miso_fuelmix_api", conn=conn, start=today, end=tomorrow
    )
    fm_df = clean_data_frame(
        fm_df, start=today, end=tomorrow, delta=dt.timedelta(minutes=5)
    )
    fm_df["start"] = fm_df["start"].dt.tz_convert(tz)

    fuel_cols = [
        col for col in fm_df.columns if col not in ("start", "end", "total")
    ]

    # "area" plot doesn't correctly exclude nans
    # manually replace nans w/ 0.0 to show gaps in data
    fm_df[fuel_cols] = fm_df[fuel_cols].fillna(0.0)

    fig = px.area(
        fm_df,
        x="start",
        y=fuel_cols,
        range_x=(today, tomorrow),
        title=f'{today.strftime("%d %B %Y")}: MISO Fuel Mix',
        labels={"start": "Time (EST)", "value": "Generation (MW)"},
    )

    return fig


def miso_lmp_plot(hub: str, conn: psycopg2.extensions.connection) -> go.Figure:

    tz = pytz.timezone("EST")
    today = dt.datetime.now(tz).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    tomorrow = today + dt.timedelta(days=1)

    rt_lmp_df = get_data_from_table(
        table="miso_realtime_expost_lmp_api",
        conn=conn,
        start=today,
        end=tomorrow,
    )
    rt_lmp_df = rt_lmp_df[rt_lmp_df["node"] == hub]
    rt_lmp_df = clean_data_frame(
        rt_lmp_df, start=today, end=tomorrow, delta=dt.timedelta(minutes=5)
    )
    rt_lmp_df["start"] = rt_lmp_df["start"].dt.tz_convert(tz)

    da_lmp_df = get_data_from_table(
        table="miso_dayahead_exante_lmp_market_report",
        conn=conn,
        start=today,
        end=tomorrow,
    )
    da_lmp_df = da_lmp_df[da_lmp_df["node"] == hub]
    da_lmp_df = clean_data_frame(
        da_lmp_df, start=today, end=tomorrow, delta=dt.timedelta(hours=1)
    )
    da_lmp_df["start"] = da_lmp_df["start"].dt.tz_convert(tz)

    fig = go.Figure(
        layout={
            "title": (
                f"{today.strftime('%d %B %Y')}: "
                f"MISO Locational Marginal Price ({hub})"
            ),
            "xaxis": {"range": [today, tomorrow], "title": "Time (EST)"},
            "yaxis": {"title": "LMP ($ / MWh)"},
        }
    )

    fig.add_scatter(
        x=rt_lmp_df["start"],
        y=rt_lmp_df["lmp"],
        mode="lines",
        name="Real-Time (Ex-Post) LMP",
    )
    fig.add_scatter(
        x=da_lmp_df["start"],
        y=da_lmp_df["lmp"],
        mode="lines",
        name="Day-Ahead (Ex-Ante) LMP",
    )

    return fig
