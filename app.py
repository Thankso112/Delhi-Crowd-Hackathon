"""Streamlit app:  streamlit run app.py      (DATA_MODE=synthetic streamlit run app.py  for the demo data)"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pandas as pd, streamlit as st, folium, seaborn as sns, matplotlib.pyplot as plt
from streamlit_folium import st_folium
import config
from planner.engine import Planner

st.set_page_config(page_title="Which bus has room?", page_icon="🚌", layout="wide")
COL = {"seats": "#14806A", "standing": "#B77900", "crowded": "#C0332B", "unknown": "#6B7B8C"}
BG = {"seats": "#DDF1EB", "standing": "#FBEFD2", "crowded": "#F9DEDB", "unknown": "#E1E6EB"}
LBL = {"seats": "Seats available", "standing": "Standing room", "crowded": "Crowded", "unknown": "No data"}

st.markdown("""<style>
.block-container{padding-top:1.4rem;max-width:1250px}
h1{font-weight:800;letter-spacing:-.5px}
.chip{display:inline-block;padding:3px 11px;border-radius:99px;font-weight:700;font-size:.85rem}
.card{background:#fff;border:1px solid #C9D2DB;border-radius:10px;padding:14px 16px;margin-bottom:10px}
.mins{font-size:2rem;font-weight:800;line-height:1}.mins small{font-size:.9rem;font-weight:500;color:#5A6B7F}
.rt{display:inline-block;background:#12263F;color:#fff;font-weight:800;border-radius:5px;padding:1px 8px;margin-right:6px}
.meta{font-size:.82rem;color:#5A6B7F}
.pips{display:flex;gap:3px;margin:8px 0 4px}.pip{height:10px;flex:1;border-radius:2px;background:#D5DCE3}
.pip.mark{outline:2px solid #12263F;outline-offset:1px}
.demo{background:#FBEFD2;border-left:5px solid #B77900;padding:8px 12px;border-radius:4px;margin-bottom:10px;font-size:.9rem}
</style>""", unsafe_allow_html=True)

@st.cache_resource
def get_planner(): return Planner()
try:
    P = get_planner()
except FileNotFoundError:
    st.error("No processed data found. Run `python run_pipeline.py` first (or use DATA_MODE=synthetic for the demo)."); st.stop()

stops = P.stops.drop_duplicates("stop_name").sort_values("stop_name").reset_index(drop=True)
names = stops.stop_name.tolist()
def default(n, fallback):
    if n in names: return names.index(n)
    hit = [i for i, x in enumerate(names) if n.lower() in x.lower()]          # real GTFS names are longer, e.g. "Anand Vihar ISBT Terminal"
    return hit[0] if hit else fallback

def chip(level): return f'<span class="chip" style="background:{BG.get(level, BG["unknown"])};color:{COL.get(level, COL["unknown"])}">{LBL.get(level, "No data")}</span>'
def meter(c):
    if c["peak_load"] is None: return ""
    n, on = 10, min(10, round(c["peak_load"] / c["crush"] * 10)); mk = round(c["seats"] / c["crush"] * 10) - 1
    pips = "".join(f'<div class="pip{" mark" if i == mk else ""}" style="{"background:" + COL[c["level"]] if i < on else ""}"></div>' for i in range(n))
    return f'<div class="pips" title="about {c["peak_load"]} of {c["crush"]} passengers">{pips}</div>'

def option_card(o):
    legs = ""
    for l in o["legs"]:
        c = l["crowd"]
        legs += f"""<div style="margin-top:12px;padding-top:10px;border-top:1px dashed #C9D2DB"><span class="rt">{l['route']}</span>{l['from_stop']} to {l['to_stop']}
        <span class="meta">({l['n_stops']} stops, about {round(l['ride_min'])} min, wait about {round(l['wait_min'])} min)</span>{meter(c)}
        <div class="meta">{chip(c['level'])} {'AC' if c['is_ac'] else 'Non-AC'} bus. Typical peak load about {c['peak_load'] if c['peak_load'] is not None else '?'} people, {c['seats']} seats.
        Source: {c['source']}, {c['n_tickets']} tickets observed. The outlined bar marks where seats run out.</div></div>"""
    conf = {"high": "High confidence", "medium": "Medium confidence", "low": "Low confidence: thin data"}[o["confidence"]]
    change = f" · {o['transfers']} change" if o["transfers"] else " · direct"
    st.markdown(f"""<div class="card"><div style="display:flex;justify-content:space-between;align-items:baseline">
      <div class="mins">{o['total_min']}<small> min{change}</small></div>{chip(o['crowd_level'])}</div>
      <div class="meta">Walk {o['walk_to_first_m']} m to the first stop and {o['walk_from_last_m']} m at the end{f", {o['transfer_walk_m']} m between buses" if o['transfers'] else ""}. <b>{conf}.</b></div>{legs}</div>""", unsafe_allow_html=True)

def option_map(o, a, b, key):
    m = folium.Map(location=[(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], zoom_start=12, tiles="OpenStreetMap", control_scale=True)
    pts = [a, b]
    for l in o["legs"]:
        folium.PolyLine(l["path"], color=COL.get(l["crowd"]["level"], COL["unknown"]), weight=6, opacity=.9, tooltip=f"Route {l['route']}: {LBL.get(l['crowd']['level'])}").add_to(m)
        pts += l["path"]
    folium.CircleMarker(a, radius=8, color="#12263F", fill=True, fill_color="#fff", fill_opacity=1, tooltip="Start").add_to(m)
    folium.CircleMarker(b, radius=8, color="#12263F", fill=True, fill_color="#12263F", fill_opacity=1, tooltip="Destination").add_to(m)
    m.fit_bounds([[min(p[0] for p in pts), min(p[1] for p in pts)], [max(p[0] for p in pts), max(p[1] for p in pts)]], padding=(30, 30))
    st_folium(m, height=470, use_container_width=True, key=key, returned_objects=[])

st.title("Which bus has room?")
st.caption("Delhi buses ranked by travel time and by how full they usually are. Typical crowding from October 2026 ticket data, not live.")
if config.MODE == "synthetic":
    st.markdown('<div class="demo"><b>Demo data.</b> Synthetic tickets and a toy network. Do not read these crowd levels as real.</div>', unsafe_allow_html=True)

tab_plan, tab_op, tab_how = st.tabs(["Plan a trip", "Operator view", "How it works"])

with tab_plan:
    with st.form("trip"):
        c1, c2, c3, c4, c5 = st.columns([2, 2, 1, 1, 1.4])
        origin = c1.selectbox("From", names, index=default("Anand Vihar ISBT", 0))
        dest = c2.selectbox("To", names, index=default("Connaught Place", min(1, len(names) - 1)))
        when = c3.time_input("Leave at", value=pd.Timestamp("18:00").time())
        day = c4.radio("Day", ["weekday", "weekend"], horizontal=False)
        mode = c5.radio("Priority", ["Faster", "More comfortable"])
        go = st.form_submit_button("Find buses", type="primary")
    if go:
        o_, d_ = stops[stops.stop_name == origin].iloc[0], stops[stops.stop_name == dest].iloc[0]
        st.session_state["res"] = dict(
            a=(float(o_.lat), float(o_.lon)), b=(float(d_.lat), float(d_.lon)),
            r=P.plan((float(o_.lat), float(o_.lon)), (float(d_.lat), float(d_.lon)), when.strftime("%H:%M"), day, "comfort" if mode == "More comfortable" else "fast"))
    res = st.session_state.get("res")
    if res:
        opts = res["r"].get("options", [])
        if not opts:
            st.warning(res["r"].get("note") or "No direct or one-transfer bus journey found for this pair.")
        else:
            tabs = st.tabs([f"Option {i + 1}: {o['total_min']} min, {LBL.get(o['crowd_level'])}" for i, o in enumerate(opts)])
            for i, (t, o) in enumerate(zip(tabs, opts)):
                with t:
                    left, right = st.columns([1, 1.15])
                    with left: option_card(o)
                    with right: option_map(o, res["a"], res["b"], key=f"map{i}")

with tab_op:
    c1, c2 = st.columns(2)
    d = c1.selectbox("Day type", ["weekday", "weekend"], key="opd")
    bnd = c2.selectbox("Time band", list(config.BANDS), index=list(config.BANDS).index("pm_peak"), key="opb")
    df = pd.DataFrame(P.operator_view(d, bnd, top=15))
    if len(df):
        fig, ax = plt.subplots(figsize=(7, 4)); df["label"] = df.route.astype(str) + " (dir " + df.dir.astype(str) + ")"
        sns.barplot(data=df, y="label", x="peak_load", hue="level", palette={k: COL[k] for k in ("seats", "standing", "crowded")}, dodge=False, ax=ax)
        ax.set(xlabel="typical peak load on the busiest stretch (adjusted)", ylabel="", title="Most loaded route-directions"); ax.legend(title="")
        st.pyplot(fig); st.dataframe(df[["route", "dir", "peak_load", "level", "n_tickets"]], hide_index=True, width="stretch")
    else:
        st.info("No data for this combination.")

with tab_how:
    st.markdown(f"""**How the crowd level is made.** Tickets have stop names but no trip or stop IDs. We match names to each route's stops, infer trips per vehicle,
    and compute the running number of passengers on board along each route (boarding adds, alighting subtracts). Loads are averaged by route, stretch, time band and day type,
    thinly observed cells are pulled toward the route average, then compared with assumed capacity: AC {config.CAPACITY['ac']['seats']} seats / {config.CAPACITY['ac']['crush']} crush,
    non-AC {config.CAPACITY['nonac']['seats']} / {config.CAPACITY['nonac']['crush']}. The ticket file is a thin sample of ridership, so ticket counts are scaled to riders with a calibration factor (see below). Capacities and the factor are assumptions, not data; the ranking of buses does not depend on them.""")
    cal = config.PROC / "calibration.json"
    if cal.exists(): st.caption("Calibration: " + json.loads(cal.read_text())["method"])
    mfile = config.OUT / "metrics.json"
    if mfile.exists():
        st.subheader("Validation metrics"); st.json(json.loads(mfile.read_text()), expanded=False)
        figs = sorted((config.OUT / "figures").glob("*.png"))
        cols = st.columns(max(1, len(figs)))
        for col, f in zip(cols, figs): col.image(str(f), width="stretch")
