"""Generate a SYNTHETIC GTFS + ticket dataset in the same format as the real data.
Purpose: test the pipeline and demo the UI when the real data is not available.
Synthetic numbers must NEVER be reported as findings. Run: python scripts/00_make_synthetic.py
"""
import os, random
from pathlib import Path
import numpy as np, pandas as pd

OUTDIR = Path(__file__).resolve().parents[1] / "data" / "synthetic"
G = OUTDIR / "gtfs"; G.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(7); random.seed(7)

PLACES = {  # approximate coordinates, for realism of geometry only
 "Anand Vihar ISBT": (28.6469, 77.3160), "Karkardooma": (28.6481, 77.3050), "Preet Vihar": (28.6410, 77.2950),
 "ITO": (28.6290, 77.2410), "Delhi Gate": (28.6400, 77.2400), "Mandi House": (28.6250, 77.2340),
 "Connaught Place": (28.6315, 77.2167), "Janpath": (28.6250, 77.2190), "Karol Bagh": (28.6519, 77.1907),
 "Patel Nagar": (28.6450, 77.1700), "Rajouri Garden": (28.6492, 77.1220), "Tilak Nagar": (28.6390, 77.0900),
 "Kashmere Gate ISBT": (28.6670, 77.2290), "Civil Lines": (28.6770, 77.2250), "Azadpur": (28.7070, 77.1760),
 "Rohini Sector 7": (28.7050, 77.1230), "Pitampura": (28.7010, 77.1310), "Nehru Place": (28.5480, 77.2530),
 "Lajpat Nagar": (28.5700, 77.2430), "AIIMS": (28.5670, 77.2090), "Saket": (28.5240, 77.2060),
 "Hauz Khas": (28.5430, 77.2000), "Dwarka Sector 21": (28.5520, 77.0580), "Janakpuri": (28.6290, 77.0850),
 "Uttam Nagar": (28.6210, 77.0550), "Laxmi Nagar": (28.6300, 77.2770), "Shahdara": (28.6730, 77.2890),
 "Noida Mor": (28.5900, 77.3050), "Okhla": (28.5610, 77.2700), "Kalkaji": (28.5390, 77.2590),
}
names = list(PLACES)
# routes as sequences of places (each direction is its reverse)
ROUTES = {
 "534": ["Anand Vihar ISBT","Karkardooma","Preet Vihar","ITO","Mandi House","Connaught Place"],
 "429": ["Anand Vihar ISBT","Laxmi Nagar","Delhi Gate","ITO","Connaught Place","Karol Bagh","Patel Nagar","Rajouri Garden","Tilak Nagar"],
 "764": ["Kashmere Gate ISBT","Civil Lines","Azadpur","Pitampura","Rohini Sector 7"],
 "712": ["Kashmere Gate ISBT","Connaught Place","Janpath","AIIMS","Hauz Khas","Saket"],
 "615": ["Nehru Place","Lajpat Nagar","AIIMS","Janpath","Connaught Place","Karol Bagh"],
 "850": ["Dwarka Sector 21","Janakpuri","Uttam Nagar","Tilak Nagar","Rajouri Garden","Patel Nagar"],
 "905": ["Shahdara","Laxmi Nagar","Preet Vihar","ITO","Mandi House"],
 "320": ["Okhla","Kalkaji","Nehru Place","Lajpat Nagar","Hauz Khas","Saket"],
 "118": ["Azadpur","Karol Bagh","Connaught Place","Delhi Gate","Noida Mor"],
}
AC = {"534": 0, "429": 0, "764": 1, "712": 1, "615": 0, "850": 0, "905": 0, "320": 1, "118": 0}
# one stop_id per (place, direction) so stop ids differ by direction like real data
stops = []
sid = {}
for n, (la, lo) in PLACES.items():
    for d in (0, 1):
        i = len(stops) + 1
        sid[(n, d)] = i
        stops.append((i, f"{n}" if d == 0 else f"{n}", la + (0.0003 if d else 0), lo + (0.0003 if d else 0)))
pd.DataFrame(stops, columns=["stop_id", "stop_name", "stop_lat", "stop_lon"]).to_csv(G / "stops.txt", index=False)
pd.DataFrame({"route_id": range(1, len(ROUTES)+1), "route_short_name": list(ROUTES), "route_type": 3}).to_csv(G / "routes.txt", index=False)
rid = {r: i+1 for i, r in enumerate(ROUTES)}

def hav(a, b):
    la1, lo1, la2, lo2 = map(np.radians, (*a, *b))
    h = np.sin((la2-la1)/2)**2 + np.cos(la1)*np.cos(la2)*np.sin((lo2-lo1)/2)**2
    return 6371000*2*np.arcsin(np.sqrt(h))

# headway profile: trips per hour per route-direction
def trips_per_hour(h): return {5:1,6:2,7:3,8:3,9:3,10:2,11:2,12:2,13:2,14:2,15:2,16:3,17:3,18:3,19:3,20:2,21:1}.get(h, 0)
trip_rows, st_rows, plan = [], [], []
tid = 0
for r, seq in ROUTES.items():
    for d in (0, 1):
        s = seq if d == 0 else seq[::-1]
        cum = [0.0]
        for a, b in zip(s[:-1], s[1:]):
            cum.append(cum[-1] + hav(PLACES[a], PLACES[b]) / 4.2 + 45)  # ~15 km/h + dwell
        for h in range(5, 22):
            n = trips_per_hour(h)
            for k in range(n):
                tid += 1
                t0 = h*3600 + int(k * 3600 / max(n, 1))
                trip_rows.append((rid[r], f"svc", tid, d))
                for q, (place, c) in enumerate(zip(s, cum)):
                    t = t0 + int(c); hh, mm, ss = t//3600, (t % 3600)//60, t % 60
                    st_rows.append((tid, f"{hh:02d}:{mm:02d}:{ss:02d}", f"{hh:02d}:{mm:02d}:{ss:02d}", sid[(place, d)], q+1))
                plan.append((r, d, tid, t0, s, cum))
pd.DataFrame(trip_rows, columns=["route_id", "service_id", "trip_id", "direction_id"]).to_csv(G / "trips.txt", index=False)
pd.DataFrame(st_rows, columns=["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"]).to_csv(G / "stop_times.txt", index=False)

# ------- tickets: Oct 1-31 2026 -------
def noisy(n):
    x = n
    c = random.random()
    if c < .12: x = x.upper()
    elif c < .22: x = x.lower()
    if random.random() < .08: x = x.replace("ISBT", "I.S.B.T.")
    if random.random() < .05: x = x.replace("Sector", "Sec")
    if random.random() < .05: x = x + " "
    if random.random() < .04: x = x.replace("Nagar", "Ngr")
    return x
DEM = {5:.4,6:.7,7:1.5,8:2.2,9:2.0,10:1.1,11:.9,12:.9,13:.9,14:1.0,15:1.3,16:1.8,17:2.4,18:2.5,19:1.7,20:1.0,21:.6}
pop = {p: rng.uniform(.5, 2.0) for p in PLACES}
for p in ("Anand Vihar ISBT", "Connaught Place", "Karol Bagh", "Kashmere Gate ISBT"): pop[p] *= 2.2
rows = []
vehicles = {(r, d): [f"DL1PC{rid[r]}{d}{i:02d}" for i in range(12)] for r in ROUTES for d in (0, 1)}
for day in pd.date_range("2026-10-01", "2026-10-31"):
    wk = day.dayofweek < 5
    dayscale = 1.0 if wk else 0.6
    for (r, d, trip, t0, s, cum) in plan:
        h = t0 // 3600
        dem = DEM.get(h, .5) * dayscale
        # directional peaks: towards centre in AM, away in PM
        central = {"Connaught Place", "Karol Bagh", "ITO", "Mandi House"}
        towards = s[-1] in central
        dirf = (1.5 if towards else .7) if h < 11 else (0.7 if towards else 1.5) if h >= 16 else 1.0
        veh = vehicles[(r, d)][trip % 12]
        for q in range(len(s) - 1):
            lam = 3.6 * dem * dirf * pop[s[q]] * rng.uniform(.8, 1.2)
            nb = rng.poisson(lam)
            for _ in range(nb):
                a = min(len(s)-1, q + 1 + int(rng.geometric(.35)) - 1)
                t = day + pd.Timedelta(seconds=int(t0 + cum[q] + rng.integers(-60, 60)))
                free = rng.random() < .35
                end = noisy(s[a]) if rng.random() > .03 else ""
                rows.append((int(rng.choice([1, 1, 1, 2])), 0 if free else int(5 * rng.integers(1, 5)),
                             veh, int(rng.choice([1, 2])) if not free else 3, noisy(s[q]), end, r, t, AC[r]))
df = pd.DataFrame(rows, columns=["passenger_count", "amount", "vehicle_number", "ticket_type_id",
                                 "start_stop_name", "end_stop_name", "route", "created_at", "is_ac"])
df = df.sort_values("created_at")
df.to_csv(OUTDIR / "tickets.csv", index=False)
print("synthetic tickets:", len(df), "->", OUTDIR)
