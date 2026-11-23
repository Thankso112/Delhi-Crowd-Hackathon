"""Load and clean the raw ticket CSV."""
import numpy as np
import pandas as pd
import config


def detect_offdays(df):
    """Find Mon-Fri days that behave like holidays: far fewer tickets than a normal weekday.
    Returns a DataFrame[date, tickets, ratio] (ratio = tickets / typical weekday)."""
    daily = df.groupby("date").size().rename("tickets").to_frame()
    daily["is_weekday"] = pd.to_datetime(daily.index).dayofweek < 5
    typical = daily.loc[daily.is_weekday, "tickets"].median()
    daily["ratio"] = daily.tickets / typical
    return daily[daily.is_weekday & (daily.ratio < config.HOLIDAY_RATIO)][["tickets", "ratio"]].reset_index()


def load_tickets_csv(path=None):
    """Read the ticket CSV with pandas and return a clean DataFrame:
    pax, amount, vehicle, ttype, start_name, end_name, route_raw, ts, is_ac, date, hour, dow (0=Monday), daytype."""
    C = config.COL
    path = path or config.TICKETS_CSV
    cat = {C[k]: "category" for k in ("vehicle", "start", "end", "route", "ttype")}
    df = pd.read_csv(path, usecols=list(C.values()), dtype=cat, low_memory=False, na_values=["NULL", ""])
    missing = [v for v in C.values() if v not in df.columns]
    assert not missing, f"Columns missing from CSV: {missing}. Edit config.COL."
    out = pd.DataFrame({
        "pax": pd.to_numeric(df[C["pax"]], errors="coerce"),
        "amount": pd.to_numeric(df[C["amount"]], errors="coerce"),
        "vehicle": df[C["vehicle"]],
        "ttype": df[C["ttype"]].astype(str).astype("category"),
        "start_name": df[C["start"]],
        "end_name": df[C["end"]],
        "route_raw": df[C["route"]].astype(str).astype("category"),
        # keep the local clock time; drop any "+05:30" suffix
        "ts": pd.to_datetime(df[C["ts"]].astype(str).str[:19], errors="coerce"),
        "is_ac": df[C["ac"]].astype(str).str.lower().isin(["1", "true", "t", "yes", "y", "ac", "1.0"]).astype(int),
    })
    out = out[out.ts.notna() & out.route_raw.notna() & (out.pax > 0)].copy()
    out["pax"] = out.pax.astype(int)
    out["date"] = out.ts.dt.strftime("%Y-%m-%d")
    out["hour"] = out.ts.dt.hour
    out["dow"] = out.ts.dt.dayofweek
    off = set(detect_offdays(out).date)
    # daytype: "weekend" = Saturday, Sunday or a holiday-like weekday; "weekday" = everything else
    out["daytype"] = np.where((out.dow >= 5) | out.date.isin(off), "weekend", "weekday")
    return out.reset_index(drop=True)
