"""Second V4 patch (run AFTER apply_v4_patch.py, from the repo root):  python apply_v4_patch2.py

1. Plan ranking: a leg with no crowd estimate used to get the penalty of the BEST tier (zero), which favoured journeys we know nothing about.
   It now gets the 'standing' penalty (still halved because its confidence is low).
2. hourly_network.overloaded_count: now the number of distinct routes with a crowded stretch backed by medium/high-confidence tickets,
   instead of the count of every crowded stretch-hour (which included thin, scaled-up cells and gave numbers like 11,286 at 05:00).

All-or-nothing: every anchor must be found exactly once, otherwise nothing is changed. Backups: <name>.bak2"""
import sys
from pathlib import Path

root = Path.cwd()
SERVING = root / "src" / "serving.py"
PLANNER = root / "src" / "planner.py"

EDITS = {
    SERVING: [
        (r'''& ct.load_ratio.notna(), ["hour", "load_ratio", "n_sched", "crowd_level"]]''',
         r'''& ct.load_ratio.notna(), ["hour", "load_ratio", "n_sched", "crowd_level", "route_n", "ticket_count"]]'''),
        (r'''g = c.groupby("hour").agg(rw=("rw", "sum"), w=("n_sched", "sum"), over=("over", "sum"), cells=("load_ratio", "size"))''',
         r'''g = c.groupby("hour").agg(rw=("rw", "sum"), w=("n_sched", "sum"), over=("over", "sum"), cells=("load_ratio", "size"))
            over_routes = c[(c.crowd_level == "crowded") & (c.ticket_count >= config.CONF_MED)].groupby("hour").route_n.nunique()'''),
        (r'''overloaded_count=int(g.at[h, "over"])''',
         r'''overloaded_count=int(over_routes.get(h, 0))'''),
    ],
    PLANNER: [
        (r'''penalty = sum(PENALTY[max(0, l["_tier"])] * (0.5 if l["confidence"] == "low" else 1.0) for l in out)''',
         r'''penalty = sum(PENALTY[l["_tier"] if l["_tier"] >= 0 else 1] * (0.5 if l["confidence"] == "low" else 1.0) for l in out)'''),
    ],
}


def load(p):
    raw = p.read_bytes().decode("utf-8")
    return raw.replace("\r\n", "\n"), ("\r\n" in raw)


def main():
    work, errors = {}, []
    for path, edits in EDITS.items():
        if not path.exists():
            errors.append(f"missing file: {path}  (run this from the repo root)")
            continue
        text, crlf = load(path)
        if "hourly_network" not in text and path == SERVING:
            errors.append("serving.py does not contain hourly_network: run apply_v4_patch.py first")
            continue
        if "over_routes" in text or "if l[\"_tier\"] >= 0 else 1" in text:
            errors.append(f"{path.name}: patch 2 already applied")
            continue
        for i, (old, new) in enumerate(edits, 1):
            n = text.count(old)
            if n != 1:
                errors.append(f"{path.name}: anchor {i} found {n} times (expected 1): {old[:70]}...")
            else:
                text = text.replace(old, new)
        work[path] = (text, crlf)
    if errors:
        print("NOTHING WAS CHANGED. Problems:")
        for e in errors:
            print(" -", e)
        sys.exit(1)
    for path, (text, crlf) in work.items():
        Path(str(path) + ".bak2").write_bytes(path.read_bytes())
        path.write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))
        print("patched", path.relative_to(root), "(backup: " + path.name + ".bak2)")
    print("Done. Now run: python verify_v4_patch.py")


main()
