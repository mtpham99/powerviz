import asyncio
import os

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

from powerviz.miso import MISOClient


def get_table_columns(  # pylint: disable=duplicate-code
    table: str,
    conn: psycopg2.extensions.connection,
) -> tuple[str]:
    columns: tuple[str]
    with conn:
        with conn.cursor() as cursor:
            sql = (
                "SELECT column_name FROM information_schema.columns "
                f"WHERE table_name = '{table}';"
            )
            cursor.execute(sql)
            columns = tuple(col[0] for col in cursor.fetchall())
    return columns


async def update_miso_db(
    conn: psycopg2.extensions.connection, client: MISOClient
) -> None:

    miso_tables_data_getters = {  # key=table name val=data method and args
        "miso_load_api": (client.get_load_data, ("today",)),
        "miso_forecast_api": (client.get_forecast_data, ("today",)),
        "miso_fuelmix_api": (client.get_fuel_mix_data, ("latest",)),
        "miso_realtime_expost_lmp_api": (
            client.get_realtime_lmp_data,
            ("today",),
        ),
        "miso_dayahead_exante_lmp_market_report": (
            client.get_dayahead_lmp_data,
            ("today",),
        ),
    }

    miso_data = dict(
        zip(
            miso_tables_data_getters.keys(),  # table names
            await asyncio.gather(  # data frames
                *[
                    fn(*args)  # type: ignore [operator]
                    for fn, args in miso_tables_data_getters.values()
                ]
            ),
        )
    )

    for tbl, df in miso_data.items():

        table_cols = get_table_columns(tbl, conn)
        matching_cols = [col for col in table_cols if col in df.columns]
        data = [tuple(row) for row in df[matching_cols].to_numpy()]

        with conn:
            with conn.cursor() as cursor:
                # placing col names in quotes
                col_names = [f'"{col}"' for col in matching_cols]
                sql = (
                    f"INSERT INTO {tbl}({', '.join(col_names)}) "
                    "VALUES %s ON CONFLICT DO NOTHING;"
                )
                psycopg2.extras.execute_values(cursor, sql, data)


async def main() -> None:
    load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))
    conn = psycopg2.connect(  # pylint: disable=duplicate-code
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        dbname=os.environ["POSTGRES_DB"],
        host=os.environ["POSTGRES_HOST"],
    )

    client = MISOClient()
    await update_miso_db(conn, client)


if __name__ == "__main__":
    asyncio.run(main())
