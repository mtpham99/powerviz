import datetime as dt

import pandas as pd
import psycopg2


def count_rows(table: str, conn: psycopg2.extensions.connection) -> int:
    count: int
    with conn:
        with conn.cursor() as cursor:
            sql = f"SELECT COUNT(*) FROM {table};"
            cursor.execute(sql)
            count = cursor.fetchone()[0]  # type: ignore [index]

    return count


def get_tables(conn: psycopg2.extensions.connection) -> list[str]:
    tables: list[str]
    with conn:
        with conn.cursor() as cursor:
            sql = (
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public';"
            )
            cursor.execute(sql)
            tables = [tbl[0] for tbl in cursor.fetchall()]

    return tables


def get_columns(table: str, conn: psycopg2.extensions.connection) -> list[str]:
    columns: list[str]
    with conn:
        with conn.cursor() as cursor:
            sql = (
                "SELECT column_name FROM information_schema.columns "
                f"WHERE table_name = '{table}';"
            )
            cursor.execute(sql)
            columns = [col[0] for col in cursor.fetchall()]

    return columns


def get_data_from_table(
    table: str,
    conn: psycopg2.extensions.connection,
    start: dt.datetime,
    end: dt.datetime,
) -> pd.DataFrame:
    columns = get_columns(table, conn)
    df: pd.DataFrame
    with conn:
        with conn.cursor() as cursor:
            sql = f'SELECT * FROM {table} WHERE "start" >= %s AND "end" <= %s;'
            cursor.execute(sql, (start, end))
            data = cursor.fetchall()

            df = pd.DataFrame(data, columns=columns).sort_values(
                by="start", ascending=True, ignore_index=True
            )

    return df
