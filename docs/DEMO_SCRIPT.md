# Demo video script (~3 min). Record with the REAL data run, not synthetic.
| Time | Show | Say |
|---|---|---|
| 0:00–0:20 | Title + a packed bus photo or the map | Commuters see a bus number, not how full it is. We estimate crowding from ticket data. |
| 0:20–1:00 | Terminal or Jupyter running `python run_pipeline.py`; show match_report.md and resolution_report.md | Tickets have stop names but no trip or stop IDs. We match names to each route's stops, resolve direction, infer trips per vehicle, and compute load along the route. Match rate X%, Y trips inferred. |
| 1:00–2:00 | Streamlit app: Anand Vihar → Connaught Place, 18:00, weekday; show chips, seat meter, confidence; toggle Faster / More comfortable; open Operator view | Each option shows a level and a confidence flag. Comfort mode trades minutes for room. Two more corridors: [A] and [B]. |
| 2:00–2:40 | outputs/figures (hourly, stability), metrics.json, sensitivity.csv | Peaks where expected; weeks 1–2 predict weeks 3–4 with skill X over baseline; levels are stable under ±15% capacity and pass factor 1.0–1.5 except where shown. |
| 2:40–3:00 | Limitations slide | Typical not live; one month; ticketed riders; assumed capacity; least reliable on thin-data routes. Credit open-source and AI tools. |
