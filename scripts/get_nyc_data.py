"""Download one month of NYC yellow-taxi trips and turn it into model inputs.

Source: NYC Taxi & Limousine Commission trip records (paper ref. [18]).
    yellow_tripdata_2024-03.parquet   ~60 MB
    taxi_zone_lookup.csv              ~12 KB

Produces data/manhattan_od.npz with, per 20-minute slot (72 per day):
    demand_days[d, t, i]  trip requests starting in region i on weekday d
    od[t, i, i']          destination distribution (weekday average)
    frac_short[t, i]      share of trips that finish within one slot
    mu[i, i']             mean trip distance between regions (miles)
    intra[i]              mean trip distance inside a region
    drop_share[i]         share of drop-offs (used to place charging ports)

Run:  .venv/bin/python scripts/get_nyc_data.py [--groups 12]
"""
import argparse
import pathlib
import urllib.request

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.sparse.csgraph import shortest_path
from scipy.spatial.distance import squareform

BASE = "https://d37ci6vzurychx.cloudfront.net"
FILES = {"yellow_tripdata_2024-03.parquet": f"{BASE}/trip-data/yellow_tripdata_2024-03.parquet",
         "taxi_zone_lookup.csv": f"{BASE}/misc/taxi_zone_lookup.csv"}
DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
SLOT_MIN = 20
T = 24 * 60 // SLOT_MIN


def download():
    DATA.mkdir(exist_ok=True)
    for name, url in FILES.items():
        dst = DATA / name
        if not dst.exists():
            print("downloading", url)
            urllib.request.urlretrieve(url, dst)


def load_trips():
    zones = pd.read_csv(DATA / "taxi_zone_lookup.csv")
    manh = set(zones[zones.Borough == "Manhattan"].LocationID)
    cols = ["tpep_pickup_datetime", "tpep_dropoff_datetime", "PULocationID", "DOLocationID", "trip_distance"]
    df = pd.read_parquet(DATA / "yellow_tripdata_2024-03.parquet", columns=cols)
    df = df[df.PULocationID.isin(manh) & df.DOLocationID.isin(manh)]
    df = df[(df.tpep_pickup_datetime.dt.month == 3) & (df.tpep_pickup_datetime.dt.dayofweek < 5)]
    df["dur_min"] = (df.tpep_dropoff_datetime - df.tpep_pickup_datetime).dt.total_seconds() / 60
    df = df[(df.dur_min > 0.5) & (df.dur_min < 120) & (df.trip_distance > 0) & (df.trip_distance < 30)]
    return df


def cluster_zones(df, groups):
    """Group TLC zones into `groups` regions using trip distances between zones.

    ASSUMPTION: the paper uses 38 Con Edison grid networks [16]; their boundaries
    are not published as a zone list, so we build geographic regions from the data.
    """
    busy = pd.concat([df.PULocationID, df.DOLocationID]).value_counts()
    zones = np.sort(busy[busy >= 200].index.to_numpy())          # drops near-empty zones (islands)
    pos = {z: k for k, z in enumerate(zones)}
    d = df[df.PULocationID.isin(pos) & df.DOLocationID.isin(pos)]
    med = d.groupby(["PULocationID", "DOLocationID"]).trip_distance.agg(["median", "size"])
    med = med[med["size"] >= 10]
    Z = len(zones)
    M = np.full((Z, Z), np.inf)
    for (a, b), row in med.iterrows():
        M[pos[a], pos[b]] = row["median"]
    M = np.minimum(M, M.T)
    np.fill_diagonal(M, 0)
    M = shortest_path(np.where(np.isinf(M), 0, M), directed=False)   # fill rare pairs
    labels = fcluster(linkage(squareform(M, checks=False), "average"), groups, "maxclust") - 1
    return zones, labels


def build(groups):
    df = load_trips()
    zones, labels = cluster_zones(df, groups)
    g = dict(zip(zones, labels))
    df = df[df.PULocationID.isin(g) & df.DOLocationID.isin(g)].copy()
    df["o"] = df.PULocationID.map(g)
    df["d"] = df.DOLocationID.map(g)
    df["t"] = (df.tpep_pickup_datetime.dt.hour * 60 + df.tpep_pickup_datetime.dt.minute) // SLOT_MIN
    df["day"] = df.tpep_pickup_datetime.dt.date
    days = sorted(df.day.unique())
    G = labels.max() + 1

    demand_days = np.zeros((len(days), T, G))
    di = df.day.map({d: k for k, d in enumerate(days)}).to_numpy()
    np.add.at(demand_days, (di, df.t.to_numpy(), df.o.to_numpy()), 1)

    counts = np.zeros((T, G, G))
    np.add.at(counts, (df.t.to_numpy(), df.o.to_numpy(), df.d.to_numpy()), 1)
    od = counts / np.maximum(counts.sum(2, keepdims=True), 1)
    od[counts.sum(2) == 0] = np.eye(G)[np.where(counts.sum(2) == 0)[1]]

    short = np.zeros((T, G))
    np.add.at(short, (df.t.to_numpy(), df.o.to_numpy()), (df.dur_min < SLOT_MIN).to_numpy())
    frac_short = short / np.maximum(counts.sum(2), 1)

    dist = df.groupby(["o", "d"]).trip_distance.mean()
    mu = np.zeros((G, G))
    for (a, b), v in dist.items():
        mu[a, b] = v
    mu = (mu + mu.T) / 2
    intra = np.diag(mu).copy()
    np.fill_diagonal(mu, 0)
    drop_share = np.bincount(df.d, minlength=G) / len(df)

    np.savez(DATA / "manhattan_od.npz", demand_days=demand_days, od=od, frac_short=frac_short,
             mu=mu, intra=intra, drop_share=drop_share, zones=zones, labels=labels,
             days=np.array([str(d) for d in days]))
    print(f"{len(df):,} weekday trips over {len(days)} days, {len(zones)} zones -> {G} regions")
    print(f"region sizes (zones): {np.bincount(labels).tolist()}")
    print(f"avg demand 17:20-19:20: {demand_days[:, 52:58].sum(2).mean():.0f} trips/slot; "
          f"trips shorter than one slot: {100 * (df.dur_min < SLOT_MIN).mean():.0f}%")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--groups", type=int, default=12)
    args = ap.parse_args()
    download()
    build(args.groups)
