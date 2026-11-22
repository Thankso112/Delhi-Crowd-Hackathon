"""
MySQL helpers.  Everything the notebooks save goes into MySQL tables, and later notebooks
(and the app) read them back with SQL.

    from src import db
    engine = db.get_engine()
    db.save_table(df, "tickets", engine)
    df = db.query("SELECT route, COUNT(*) FROM tickets GROUP BY route", engine)
"""
import pandas as pd
from urllib.parse import quote_plus
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.types import String, Float, Integer, DateTime, Date
from sqlalchemy.exc import OperationalError
import config

_HELP = """
Could not connect to MySQL.  Checklist:
  1. Is MySQL running?  (Windows: open 'Services' and start 'MySQL80', or run  net start MySQL80  as admin)
  2. Did you copy .env.example to .env and type your real password?
  3. No MySQL yet?  Set USE_MYSQL=0 in .env to use a local SQLite file for now.
Original error: {err}
"""


def get_engine():
    """Return a SQLAlchemy engine. Creates the database (bus_crowd_<mode>) if it does not exist."""
    if not config.USE_MYSQL:
        return create_engine(f"sqlite:///{config.SQLITE_FILE}")
    server = (f"mysql+pymysql://{config.MYSQL_USER}:{quote_plus(config.MYSQL_PASSWORD)}"
              f"@{config.MYSQL_HOST}:{config.MYSQL_PORT}")
    try:
        with create_engine(server).connect() as c:
            c.execute(text(f"CREATE DATABASE IF NOT EXISTS `{config.DB_NAME}` CHARACTER SET utf8mb4"))
    except OperationalError as e:
        raise RuntimeError(_HELP.format(err=e)) from e
    return create_engine(f"{server}/{config.DB_NAME}?charset=utf8mb4", pool_pre_ping=True)


def _dtypes(df):
    """Pick sensible SQL column types so text columns can be indexed (VARCHAR instead of TEXT)."""
    out = {}
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_datetime64_any_dtype(s):
            out[c] = DateTime()
        elif pd.api.types.is_bool_dtype(s):
            out[c] = Integer()
        elif pd.api.types.is_float_dtype(s):
            out[c] = Float()
        elif pd.api.types.is_integer_dtype(s):
            out[c] = Integer()
        else:
            width = int(s.astype(str).str.len().max() or 1)
            out[c] = String(min(max(width + 10, 20), 255))
    return out


ARTIFACT_TABLES = {"route_patterns", "route_hourly", "route_attrs", "route_meta"}      # also written as Parquet so the API needs no database


def save_table(df, name, engine, index_cols=None):
    """Write a DataFrame to a MySQL table (replacing it) and add indexes on index_cols."""
    df = df.copy()
    for c in df.columns:                       # category -> plain text so SQL can store it
        if isinstance(df[c].dtype, pd.CategoricalDtype):
            df[c] = df[c].astype(object)
    # method=None -> "executemany": the MySQL driver sends rows in big batches (about 5x faster than method="multi")
    df.to_sql(name, engine, if_exists="replace", index=False, chunksize=20000, dtype=_dtypes(df))
    for col in (index_cols or []):          # one index per column makes WHERE / GROUP BY on it fast
        with engine.begin() as c:
            c.execute(text(f"CREATE INDEX idx_{name}_{col} ON `{name}` (`{col}`)"))
    if name in ARTIFACT_TABLES:
        try:
            (config.OUT / "artifacts").mkdir(exist_ok=True)
            df.to_parquet(config.OUT / "artifacts" / f"{name}.parquet", index=False)
        except Exception as e:                                              # pyarrow missing -> the API simply reads the database
            print(f"(parquet copy of {name} skipped: {e})")
    return len(df)


def query(sql, engine, params=None):
    """Run a SELECT and return a DataFrame."""
    with engine.connect() as c:
        return pd.read_sql(text(sql), c, params=params)


def read_table(name, engine):
    return query(f"SELECT * FROM `{name}`", engine)


def table_exists(name, engine):
    return name in inspect(engine).get_table_names()


def describe_database(engine):
    """Return a DataFrame listing every table, its columns and row count (used for the documentation)."""
    insp, rows = inspect(engine), []
    for t in sorted(insp.get_table_names()):
        n = query(f"SELECT COUNT(*) AS n FROM `{t}`", engine).n[0]
        cols = ", ".join(f"{c['name']}" for c in insp.get_columns(t))
        rows.append(dict(table=t, rows=int(n), columns=cols))
    return pd.DataFrame(rows)
