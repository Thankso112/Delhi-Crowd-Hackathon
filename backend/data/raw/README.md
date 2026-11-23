# Put the raw data here (not stored in git - too large)

```
data/raw/tickets.csv            <- October-Delhi.csv  (from the hackathon's October-Delhi.csv.zip, ~290 MB, 2,559,899 rows)
data/raw/gtfs/stops.txt         <- static GTFS "Delhi Buses: GTFS Static Data - DTC / DoT"
data/raw/gtfs/routes.txt           (request it on https://delhi.transportstack.in -> Datasets -> Static)
data/raw/gtfs/trips.txt
data/raw/gtfs/stop_times.txt
```
Then run `python run_all.py --check`.   (Ignore any `._*.txt` files macOS adds to zips - they are not read.)
