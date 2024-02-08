import os

import dash_bootstrap_components as dbc
import plot as plt
import plotly.graph_objects as go
import psycopg2
from dash import Dash, Input, Output, dcc, html
from dotenv import load_dotenv

app = Dash(__name__, suppress_callback_exceptions=True)
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))
conn = psycopg2.connect(
    user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
    dbname=os.environ["POSTGRES_DB"],
    host=os.environ["POSTGRES_HOST"],
)


app.layout = html.Div(
    [dcc.Location(id="url", refresh=False), html.Div(id="page-content")]
)

navigation_buttons = dbc.Row(
    [
        dbc.Col(
            html.Div(
                [
                    dcc.Link(
                        html.Button(
                            children="HOME",
                            id="home-button",
                        ),
                        href="/powerviz/",
                    ),
                    dcc.Link(
                        html.Button(
                            children="MISO",
                            id="miso-button",
                        ),
                        href="/powerviz/miso",
                    ),
                ]
            ),
        ),
    ],
)

home_page = html.Div(
    [
        # Title
        dbc.Row(
            [
                dbc.Col(html.H1(children="Welcome to Powerviz"), width=5),
            ],
            justify="center",
        ),
        # Navigation buttons
        navigation_buttons,
    ]
)

miso_page = html.Div(
    [
        # Title
        dbc.Row(
            [
                dbc.Col(html.H1(children="Powerviz: MISO"), width=5),
                dbc.Col(width=5),
            ],
            justify="center",
        ),
        # Navigation buttons
        navigation_buttons,
        # Update Interval
        dcc.Interval(
            id="miso-update-interval",
            interval=30 * 1000,
            n_intervals=0,
            max_intervals=-1,
        ),
        # Load/Forecast Graph
        dcc.Graph(id="miso-load-forecast-plot"),
        # Fuel Mix Graph
        dcc.Graph(id="miso-fuel-mix-plot"),
        # LMP Graph
        dcc.Graph(id="miso-lmp-plot"),
        # LMP Hub Selector
        dcc.Dropdown(
            options=[
                "INDIANA.HUB",
                "ILLINOIS.HUB",
                "TEXAS.HUB",
                "MS.HUB",
                "MINNESOTA.HUB",
                "MICHIGAN.HUB",
                "ARKANSAS.HUB",
                "LOUISIANA.HUB",
            ],
            value="ILLINOIS.HUB",
            clearable=False,
            multi=False,
            id="miso-lmp-hub-dropdown",
        ),
    ]
)


@app.callback(
    Output("miso-load-forecast-plot", "figure"),
    Output("miso-fuel-mix-plot", "figure"),
    Output("miso-lmp-plot", "figure"),
    [
        Input("miso-update-interval", "n_intervals"),
        Input("miso-lmp-hub-dropdown", "value"),
    ],
)
def miso_update_plots(
    n: int, lmp_hub: str  # pylint: disable=unused-argument
) -> tuple[go.Figure, go.Figure, go.Figure]:

    load_forecast_plot = plt.miso_load_and_forecast_plot(conn).update_layout(
        {"uirevision": True}
    )
    fuel_mix_plot = plt.miso_fuel_mix_plot(conn).update_layout(
        {"uirevision": True}
    )
    lmp_plot = plt.miso_lmp_plot(lmp_hub, conn).update_layout(
        {"uirevision": True}
    )

    return (load_forecast_plot, fuel_mix_plot, lmp_plot)


@app.callback(
    Output("page-content", "children"),
    Input("url", "pathname"),
)
def display_page(pathname: str) -> html.Div:
    if pathname.endswith("/miso"):
        return miso_page
    return home_page


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=os.environ["POWERVIZ_PORT"])
