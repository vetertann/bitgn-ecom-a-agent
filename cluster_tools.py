"""Anomaly cluster detection over /bin/sql.

`anomaly_clusters()` returns a ClusterSet of spatial-temporal impossible-travel
candidates (primary bursts + nearby-date mini-bursts). The model decides
include/reject per cluster and reads `cs.refs()` for the final ref list —
no hand-typing of payment paths into submit().

SQL is coupled to the benchmark schema (columns customer_id, store_id,
created_at, observed_lat, observed_lon, basket_archived, path; joined to
stores.lat/lon). Intentional for now.
"""

import csv
import io
import math
from dataclasses import dataclass
from datetime import datetime


_ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


@dataclass
class Cluster:
    id: str
    kind: str                # "burst" | "mini-burst"
    customer_id: str
    date: str
    payments: list           # list of dict rows from SQL
    span_minutes: float
    distinct_stores: int
    spoof_km: float          # mean haversine(observed, claimed) over valid rows
    max_kmh: float           # max implied speed between consecutive payments at claimed stores

    @property
    def paths(self):
        return [p["path"] for p in self.payments if p.get("path")]

    @property
    def signals(self):
        """Human-readable reason this cluster qualifies as impossible-travel fraud."""
        flags = []
        if self.max_kmh > 200:
            flags.append(f"impossible_speed={self.max_kmh:.0f}km/h")
        if self.spoof_km >= 100:
            flags.append(f"spoofed_coords={self.spoof_km:.0f}km")
        return ", ".join(flags) if flags else "no fraud signal"


class ClusterSet:
    """Candidate clusters with model-driven verdicts.

    Methods the model uses:
      .clusters              -> list of Cluster
      .include(id, reason)   -> mark as part of the hit
      .reject(id, reason)    -> exclude with reason
      .auto_include_unverdicted()  -> default-include fallback per presubmit item 13
      .refs()                -> deduped payment paths for submit(refs=...)
      .summary()             -> human-readable verdict listing for answer text
    """

    def __init__(self, clusters):
        self.clusters = list(clusters)
        self._verdicts: dict[str, tuple[str, str]] = {}

    def __repr__(self):
        lines = [f"ClusterSet ({len(self.clusters)} clusters)"]
        for c in self.clusters:
            st, why = self._verdicts.get(c.id, ("pending", ""))
            lines.append(
                f"  [{st.upper():7}] {c.id}  kind={c.kind}  n={len(c.payments)} "
                f"stores={c.distinct_stores} span={c.span_minutes:.1f}m "
                f"spoof={c.spoof_km:.0f}km max_kmh={c.max_kmh:.0f}"
            )
            if why:
                lines.append(f"           reason: {why}")
        return "\n".join(lines)

    def include(self, cluster_id, reason):
        self._verdicts[cluster_id] = ("include", reason)

    def reject(self, cluster_id, reason):
        self._verdicts[cluster_id] = ("reject", reason)

    def auto_include_unverdicted(self):
        for c in self.clusters:
            self._verdicts.setdefault(c.id, ("include", "default-include (no explicit rejection)"))

    def refs(self):
        seen: set[str] = set()
        out: list[str] = []
        for c in self.clusters:
            if self._verdicts.get(c.id, (None,))[0] != "include":
                continue
            for path in c.paths:
                if path not in seen:
                    seen.add(path)
                    out.append(path)
        return out

    def summary(self):
        lines = []
        for c in self.clusters:
            verdict, reason = self._verdicts.get(c.id, ("pending", ""))
            head = (
                f"{verdict.upper()}: {c.id} ({c.kind}, {len(c.payments)} payments, "
                f"{c.distinct_stores} stores, span {c.span_minutes:.1f}min, "
                f"spoof {c.spoof_km:.0f}km, max_kmh {c.max_kmh:.0f})"
            )
            lines.append(f"{head} — {reason}" if reason else head)
        return "\n".join(lines)


def anomaly_clusters(
    ws,
    *,
    table: str = "payments",
    where: str = "basket_archived = 1",
    min_distinct_stores: int = 2,
    max_span_minutes: float = 10,
    mini_span_minutes: float = 30,
    spoof_km_threshold: float = 100.0,
    mini_spoof_km_threshold: float = 50.0,
    max_realistic_kmh: float = 200.0,
    nearby_days: int = 14,
    debug: bool = False,
) -> ClusterSet:
    """Find impossible-travel anomaly clusters.

    Pipeline:
    1. **Primary scan.** Group rows by (customer_id, DATE(created_at)). Keep
       groups with >= min_distinct_stores distinct stores in <= max_span_minutes.
    2. For each candidate, pull payment rows joined with store coords. Compute
       mean haversine(observed, claimed) over rows with valid coordinates. Drop
       if mean < spoof_km_threshold km. Surviving groups are classified as
       "burst" clusters.
    3. **Nearby scan.** For each burst, search dates within ± nearby_days for
       any (customer, date) group with >= min_distinct_stores distinct stores
       in <= mini_span_minutes (looser span window than primary). Excludes
       (customer, date) pairs already classified as bursts. Apply the same
       spoof check; surviving groups are classified as "mini-burst".
    4. Return ClusterSet(bursts + minis). Model decides include/reject per
       presubmit item 13.
    """
    primary_sql = f"""
    SELECT customer_id, DATE(created_at) AS d,
           COUNT(*) AS n, COUNT(DISTINCT store_id) AS sd,
           (strftime('%s', MAX(created_at)) - strftime('%s', MIN(created_at)))/60.0 AS span_min
    FROM {table} WHERE {where}
    GROUP BY customer_id, DATE(created_at)
    HAVING sd >= {min_distinct_stores} AND span_min <= {max_span_minutes}
    ORDER BY sd DESC, n DESC
    """
    primary_rows = _sql_rows(ws, primary_sql)
    bursts: list[Cluster] = []
    primary_rejected = 0
    for r in primary_rows:
        c = _build_cluster(ws, "burst", r["customer_id"], r["d"],
                           where, table, spoof_km_threshold, max_realistic_kmh)
        if c is not None:
            bursts.append(c)
        else:
            primary_rejected += 1
    if debug:
        print(f"[anomaly_clusters] primary scan: {len(primary_rows)} candidates, "
              f"{len(bursts)} qualified, {primary_rejected} rejected (no fraud signal)")

    minis: list[Cluster] = []
    seen_minis: set[tuple[str, str]] = set()
    burst_keys = {(b.customer_id, b.date) for b in bursts}
    nearby_candidates = 0
    nearby_rejected = 0
    for b in bursts:
        nearby_sql = f"""
        SELECT customer_id, DATE(created_at) AS d, COUNT(*) AS n,
               COUNT(DISTINCT store_id) AS sd,
               (strftime('%s', MAX(created_at)) - strftime('%s', MIN(created_at)))/60.0 AS span_min
        FROM {table} WHERE {where}
          AND DATE(created_at) BETWEEN DATE('{b.date}', '-{nearby_days} days')
                                   AND DATE('{b.date}', '+{nearby_days} days')
        GROUP BY customer_id, DATE(created_at)
        HAVING sd >= {min_distinct_stores} AND span_min <= {mini_span_minutes}
        ORDER BY sd DESC, n DESC
        """
        for r in _sql_rows(ws, nearby_sql):
            key = (r["customer_id"], r["d"])
            if key in seen_minis or key in burst_keys:
                continue
            seen_minis.add(key)
            nearby_candidates += 1
            c = _build_cluster(ws, "mini-burst", r["customer_id"], r["d"],
                               where, table, mini_spoof_km_threshold, max_realistic_kmh)
            if c is not None:
                minis.append(c)
            else:
                nearby_rejected += 1
    if debug:
        print(f"[anomaly_clusters] nearby scan: {nearby_candidates} candidates, "
              f"{len(minis)} qualified, {nearby_rejected} rejected (no fraud signal)")

    return ClusterSet(bursts + minis)


def _build_cluster(ws, kind, customer, date, where, table, spoof_threshold, max_realistic_kmh):
    sql = f"""
    SELECT p.id, p.path, p.store_id, p.created_at,
           p.observed_lat, p.observed_lon,
           s.lat AS claimed_lat, s.lon AS claimed_lon
    FROM {table} p LEFT JOIN stores s ON s.id = p.store_id
    WHERE {where} AND p.customer_id = '{customer}' AND DATE(p.created_at) = '{date}'
    ORDER BY p.created_at
    """
    rows = _sql_rows(ws, sql)
    if not rows:
        return None

    # Signal A: coordinate spoofing — mean haversine(observed, claimed) across rows
    dists = [_haversine_observed_to_claimed(r) for r in rows]
    valid = [d for d in dists if d is not None]
    spoof_km = sum(valid) / len(valid) if valid else 0.0

    # Signal B: impossible inter-store travel — max implied speed between
    # consecutive payments at their CLAIMED store coordinates
    max_kmh = _max_implied_kmh(rows)

    # Cluster qualifies if EITHER signal fires
    is_spoofed = spoof_km >= spoof_threshold
    is_impossible = max_kmh > max_realistic_kmh
    if not is_spoofed and not is_impossible:
        return None

    times = [r["created_at"] for r in rows if r.get("created_at")]
    span = _minutes_between(min(times), max(times)) if len(times) >= 2 else 0.0
    return Cluster(
        id=f"{kind}-{customer}-{date}",
        kind=kind,
        customer_id=customer,
        date=date,
        payments=rows,
        span_minutes=span,
        distinct_stores=len({r.get("store_id") for r in rows if r.get("store_id")}),
        spoof_km=spoof_km,
        max_kmh=max_kmh,
    )


def _max_implied_kmh(rows):
    """Max implied speed (km/h) between consecutive payments at claimed store coords.
    Rows are assumed sorted by created_at ASC. Returns 0 if fewer than 2 rows or
    no valid pairs."""
    if len(rows) < 2:
        return 0.0
    speeds: list[float] = []
    for i in range(len(rows) - 1):
        a, b = rows[i], rows[i + 1]
        try:
            lat1, lon1 = float(a["claimed_lat"]), float(a["claimed_lon"])
            lat2, lon2 = float(b["claimed_lat"]), float(b["claimed_lon"])
            t1, t2 = a["created_at"], b["created_at"]
        except (ValueError, TypeError, KeyError):
            continue
        if not t1 or not t2:
            continue
        try:
            minutes = _minutes_between(t1, t2)
        except ValueError:
            continue
        if minutes <= 0:
            # Identical timestamps or out-of-order — treat as infinite implied speed
            # only if the stores are actually different
            d = _haversine_points(lat1, lon1, lat2, lon2)
            if d > 1.0:
                speeds.append(1e6)
            continue
        d = _haversine_points(lat1, lon1, lat2, lon2)
        speeds.append((d / minutes) * 60.0)  # km/h
    return max(speeds) if speeds else 0.0


def _haversine_points(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2
         + math.cos(p1) * math.cos(p2)
         * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def _sql_rows(ws, sql):
    """Run /bin/sql; parse rendered output into list of dicts."""
    raw = ws.exec("/bin/sql", stdin=sql)
    parts = raw.split("\nSQL\n", 1)
    if len(parts) != 2:
        raise RuntimeError(f"unexpected /bin/sql output shape: {raw[:200]}")
    body = parts[1]
    if "stderr:" in body or "[exit " in body:
        raise RuntimeError(f"/bin/sql error in anomaly_clusters: {body[:400]}")
    if "[TRUNCATED:" in body:
        raise RuntimeError("/bin/sql output truncated; narrow the query or raise LIMIT")
    if not body.strip():
        return []
    reader = csv.DictReader(io.StringIO(body))
    return [dict(row) for row in reader]


def _haversine_observed_to_claimed(row):
    try:
        lat1 = float(row["observed_lat"])
        lon1 = float(row["observed_lon"])
        lat2 = float(row["claimed_lat"])
        lon2 = float(row["claimed_lon"])
    except (ValueError, TypeError, KeyError):
        return None
    return _haversine_points(lat1, lon1, lat2, lon2)


def _minutes_between(t1, t2):
    return (datetime.strptime(t2, _ISO_FORMAT)
            - datetime.strptime(t1, _ISO_FORMAT)).total_seconds() / 60.0
