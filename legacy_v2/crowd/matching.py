"""Step 3: tickets carry stop NAMES, GTFS has stop IDs. Match names to the stops of the SAME route with fuzzy string matching."""
import pandas as pd
from rapidfuzz import process, fuzz
from crowd.text import config, norm_name, norm_route

def match_stop_names(tickets: pd.DataFrame, pat: pd.DataFrame) -> pd.DataFrame:
    """One row per distinct (route, raw name) with the matched GTFS name and how it was matched."""
    a = tickets.groupby(["route_raw", "start_name"], observed=True, dropna=False).size().rename("n").reset_index().rename(columns={"start_name": "name"})
    b = tickets.groupby(["route_raw", "end_name"], observed=True, dropna=False).size().rename("n").reset_index().rename(columns={"end_name": "name"})
    tk = pd.concat([a, b]).groupby(["route_raw", "name"], dropna=False, as_index=False).n.sum()
    tk["route_raw"] = tk.route_raw.astype(str)
    tk["route_n"] = tk.route_raw.map(norm_route)
    tk["name_n"] = tk.name.map(norm_name)

    # GTFS stop names are often composite ("Laxmi Nagar Metro Station / Laxmi Nagar") while tickets use one simple form.
    # So every "/"-separated part of a GTFS name becomes an ALIAS that points back to the full GTFS name.
    alias = {}                                                       # route_n -> {alias_n: full name_n}
    for rn, nm in zip(pat.route_n, pat.stop_name):
        full = norm_name(nm); d = alias.setdefault(rn, {})
        d.setdefault(full, full)
        for part in str(nm).split("/"):
            pn = norm_name(part)
            if pn: d.setdefault(pn, full)
    nospace = {rn: {k.replace(" ", ""): v for k, v in d.items()} for rn, d in alias.items()}
    all_names = pat.drop_duplicates("name_n").name_n.tolist()
    rows = []
    for r in tk.itertuples():
        hit, score, how = None, 0.0, "none"
        if not r.name_n:
            how = "blank"
        elif r.route_n not in alias:
            how = "route_not_in_gtfs"
        else:
            al = alias[r.route_n]
            if r.name_n in al:
                hit, score, how = al[r.name_n], 100.0, "exact_route"
            else:
                keys = list(al)
                m = process.extractOne(r.name_n, keys, scorer=fuzz.token_sort_ratio)
                if m and m[1] >= config.FUZZY_ROUTE_THRESHOLD:
                    hit, score, how = al[m[0]], m[1], "fuzzy_route"
                else:
                    m = process.extractOne(r.name_n, keys, scorer=fuzz.token_set_ratio)       # ticket name is part of a longer GTFS name
                    if m and m[1] >= 95 and len(r.name_n) >= 5:
                        hit, score, how = al[m[0]], m[1], "contained_in_route_name"
                    else:
                        ns = nospace[r.route_n]; m = process.extractOne(r.name_n.replace(" ", ""), list(ns), scorer=fuzz.ratio)   # "azad pur" vs "azadpur"
                        if m and m[1] >= 92:
                            hit, score, how = ns[m[0]], m[1], "fuzzy_no_spaces"
                        else:                                                                        # last resort: any stop in Delhi
                            m = process.extractOne(r.name_n, all_names, scorer=fuzz.token_sort_ratio)
                            if m and m[1] >= config.FUZZY_GLOBAL_THRESHOLD:
                                hit, score, how = m[0], m[1], "fuzzy_global_offroute"
        rows.append((r.route_raw, r.route_n, r.name, r.name_n, hit, score, how, r.n))
    return pd.DataFrame(rows, columns=["route_raw", "route_n", "name", "name_n", "gtfs_name_n", "score", "method", "n_uses"])

def match_report(sm: pd.DataFrame) -> str:
    tot = sm.n_uses.sum()
    lines = [f"- {m}: {g.n_uses.sum():,} ({g.n_uses.sum() / tot:.1%})" for m, g in sm.groupby("method")]
    return f"# Stop-name match report\nName occurrences (start + end): {tot:,}\n" + "\n".join(lines) + \
           f"\n\nMatched share: {sm[sm.gtfs_name_n.notna()].n_uses.sum() / tot:.1%}"
