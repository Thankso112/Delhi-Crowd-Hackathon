"""Step 5a: running on-board load along every trip (the heart of the crowd model).

Idea: walk along the route. At the stop where a passenger boards, load goes UP by pax; where they alight it goes DOWN.
Put +pax at the boarding index and -pax at the alighting index in an array, then take a running sum (np.cumsum).
Load at position i = number of passengers on board between stop i and stop i+1."""
import numpy as np, pandas as pd

def load_along_trip(boardings, alightings, pax, n_stops):
    """Tiny helper used by the tests and the notebook to show the idea on ONE trip."""
    d = np.zeros(n_stops)
    np.add.at(d, boardings, pax)
    np.add.at(d, alightings, -np.asarray(pax))
    return np.cumsum(d)[: n_stops - 1]

def compute_segment_loads(tix: pd.DataFrame, trips: pd.DataFrame, pat: pd.DataFrame) -> pd.DataFrame:
    """Long table: one row per (trip, stretch) with the load on board. Done route-direction by route-direction with NumPy."""
    n_stops = pat.groupby(["route_n", "dir"]).idx.max().add(1).to_dict()
    tix_groups = dict(tuple(tix.groupby(["route_n", "dir"])))
    pieces = []
    for key, tr in trips.groupby(["route_n", "dir"]):
        n = n_stops.get(key)
        if n is None or n < 2 or key not in tix_groups:
            continue
        tx = tix_groups[key]
        rows = pd.Index(tr.trip_no.to_numpy()).get_indexer(tx.trip_no.to_numpy())     # which row of the matrix each ticket belongs to
        D = np.zeros((len(tr), n))                                                     # trips x stops
        np.add.at(D, (rows, tx.b.to_numpy()), tx.pax.to_numpy())
        np.add.at(D, (rows, tx.a.to_numpy()), -tx.pax.to_numpy())
        L = np.cumsum(D, axis=1)[:, : n - 1]                                           # running sum along each trip
        pieces.append(pd.DataFrame({"trip_no": np.repeat(tr.trip_no.to_numpy(), n - 1), "pos": np.tile(np.arange(n - 1), len(tr)), "load": L.ravel()}))
    seg = pd.concat(pieces, ignore_index=True)
    return seg.merge(trips[["trip_no", "route_n", "dir", "date", "week", "band", "daytype"]], on="trip_no")
