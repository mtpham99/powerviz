-- Create MISO Tables

-- Hub Enum Type
CREATE TYPE miso_hubs AS ENUM (
    'ARKANSAS.HUB',
    'ILLINOIS.HUB',
    'INDIANA.HUB',
    'LOUISIANA.HUB',
    'MICHIGAN.HUB',
    'MINN.HUB',
    'MS.HUB',
    'TEXAS.HUB'
);

-- Load (API)
CREATE TABLE IF NOT EXISTS miso_load_api
(
    "start" timestamptz NOT NULL,
    "end" timestamptz NOT NULL,
    load numeric(10, 2) NOT NULL,
    PRIMARY KEY ("start", "end")
);

-- Forecast (API)
CREATE TABLE IF NOT EXISTS miso_forecast_api
(
    "start" timestamptz NOT NULL,
    "end" timestamptz NOT NULL,
    forecast numeric(10, 2) NOT NULL,
    PRIMARY KEY ("start", "end")
);

-- Fuel Mix (API)
CREATE TABLE IF NOT EXISTS miso_fuelmix_api
(
    "start" timestamptz NOT NULL,
    "end" timestamptz NOT NULL,
    nuclear numeric(10, 2),
    coal numeric(10, 2),
    natural_gas numeric(10, 2),
    wind numeric(10, 2),
    solar numeric(10, 2),
    imports numeric(10,2),
    other numeric(10, 2),
    total numeric(10, 2),
    PRIMARY KEY ("start", "end")
);

-- Real-Time Ex-Post LMP (API)
CREATE TABLE IF NOT EXISTS miso_realtime_expost_lmp_api
(
    "start" timestamptz NOT NULL,
    "end" timestamptz NOT NULL,
    node miso_hubs NOT NULL,
    lmp numeric(8, 2) NOT NULL,
    mlc numeric(8, 2) NOT NULL,
    mcc numeric(8, 2) NOT NULL,
    PRIMARY KEY ("start", "end", node)
);

-- Day-Ahead Ex-Ante LMP (Market Report)
CREATE TABLE IF NOT EXISTS miso_dayahead_exante_lmp_market_report
(
    "start" timestamptz NOT NULL,
    "end" timestamptz NOT NULL,
    node miso_hubs NOT NULL,
    lmp numeric(8, 2) NOT NULL,
    mlc numeric(8, 2) NOT NULL,
    mcc numeric(8, 2) NOT NULL,
    PRIMARY KEY ("start", "end", node)
);
