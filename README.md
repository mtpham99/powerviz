# PowerViz

Webscrapers and dashboard for viewing energy/power related data from the ISO/RTOs (Independent/Regional System/Transmission Operators).


## Available Data

Currently only MISO data is avilable. Realtime data for load, generation, and LMP are shown in the dashboard, but historical data is retrievable using the "MISOClient". Examples of data retrieval are in "examples/miso_example.py".


## Quick Setup (Docker)

1. Make sure docker + docker-compose are installed
2. Add a password to the ".env_example" file and rename the file to ".env"
3. Run "sudo docker compose up -d"
4. Open a browser and navigate to "http://0.0.0.0:8050"


## Internals

Dashboard is made using [Dash (Flask + Plotly)](https://dash.plotly.com/). Data is stored using a PostgreSQL database. The dockerized Dash app, includes a cron job that runs a python script which retrieves and inserts data into the database every minute. The docker PostgreSQL database is separate from the docker Dash app.

The webscrapers utilize [Aiohttp](https://docs.aiohttp.org/en/stable/index.html) for asynchronous web requests. 


## Demonstration

https://github.com/mtpham99/powerviz/assets/72663763/f5360799-51a4-40da-98a9-697e4c2a9187


## Notes
Historical data retrieval for MISO realtime LMP is quite slow (~10s per file on my machine). The archived/zip MISO market report files are large and parsing xlsx files can be slow (calamine engine helps -- requires pandas >= 2.2).
