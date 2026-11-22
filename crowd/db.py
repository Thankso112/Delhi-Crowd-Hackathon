"""Optional: store results in a SQL database with SQLAlchemy. Default = SQLite (a single file, zero setup).
For MySQL set an environment variable first, e.g. (Anaconda Prompt):
    set DB_URL=mysql+pymysql://root:YOUR_PASSWORD@localhost:3306/busdb
(create the empty database once in MySQL:  CREATE DATABASE busdb;)  Needs: pip install sqlalchemy pymysql"""
import os
import pandas as pd
from sqlalchemy import create_engine
from crowd.text import config

def get_engine():
    return create_engine(os.environ.get("DB_URL", f"sqlite:///{config.PROC / 'crowd.db'}"))

def save_tables(tables: dict, engine=None):
    engine = engine or get_engine()
    for name, df in tables.items():
        df.to_sql(name, engine, if_exists="replace", index=False, chunksize=20000)
    return engine

def query(sql: str, engine=None) -> pd.DataFrame:
    return pd.read_sql(sql, engine or get_engine())
