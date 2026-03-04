# db/sanctions.py
"""
Vessel registry reconciliation utilities.

These functions are called exclusively from reconcile.py.
They operate on the vessels_canonical and related tables.
"""

import json

import normalize  # project root — not db/normalize.py

from .connection import _BACKEND, _conn, _cursor, _rows, _row, _ph, _ilike, _jp  # noqa: F401
from .vessels import get_vessel_memberships  # noqa: F401


# ── Reconciliation helpers ────────────────────────────────────────────────

def find_mmsi_imo_collisions() -> list[tuple[str, str]]:
    """
    Tier 2: find MMSI-keyed canonicals whose MMSI value also appears in
    an IMO-keyed canonical.  Returns list of (mmsi_canonical_id, imo_canonical_id).
    """
    with _conn() as conn:
        c = _cursor(conn)
        c.execute("""
            SELECT a.canonical_id AS mmsi_cid,
                   b.canonical_id AS imo_cid
            FROM vessels_canonical a
            JOIN vessels_canonical b
                ON a.mmsi IS NOT NULL
               AND a.mmsi = b.mmsi
               AND a.canonical_id != b.canonical_id
            WHERE a.match_method = 'mmsi_exact'
              AND b.match_method = 'imo_exact'
        """)
        return [(r["mmsi_cid"], r["imo_cid"]) for r in _rows(c)]


def find_imo_collisions() -> list[tuple[str, list[str]]]:
    """
    Tier 1 safety sweep: find multiple canonicals with the same imo_number.
    Returns list of (imo_number, [canonical_id, ...]).
    """
    with _conn() as conn:
        c = _cursor(conn)
        c.execute("""
            SELECT imo_number, COUNT(*) AS n
            FROM vessels_canonical
            WHERE imo_number IS NOT NULL
            GROUP BY imo_number
            HAVING COUNT(*) > 1
        """)
        dupes = _rows(c)

    p = "?" if _BACKEND == "sqlite" else "%s"
    result = []
    for d in dupes:
        imo = d["imo_number"]
        with _conn() as conn:
            c = _cursor(conn)
            c.execute(
                f"SELECT canonical_id FROM vessels_canonical WHERE imo_number = {p}",
                (imo,),
            )
            cids = [r["canonical_id"] for r in _rows(c)]
        result.append((imo, cids))
    return result


def merge_canonical(source_id: str, target_id: str) -> None:
    """
    Merge the source canonical into the target canonical:
      1. Reassign all memberships from source → target.
      2. Merge aliases + source_tags onto target.
      3. Promote imo_number / mmsi if source has them and target doesn't.
      4. Delete source canonical.
    """
    p        = "?" if _BACKEND == "sqlite" else "%s"
    jp       = _jp()
    now_expr = "datetime('now')" if _BACKEND == "sqlite" else "NOW()"

    with _conn() as conn:
        c = _cursor(conn)

        c.execute(
            f"SELECT aliases, source_tags, imo_number, mmsi "
            f"FROM vessels_canonical WHERE canonical_id = {p}",
            (source_id,),
        )
        src = _row(c)
        c.execute(
            f"SELECT aliases, source_tags, imo_number, mmsi "
            f"FROM vessels_canonical WHERE canonical_id = {p}",
            (target_id,),
        )
        tgt = _row(c)
        if not src or not tgt:
            return

        def _parse(val):
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except json.JSONDecodeError:
                    return []
            return val or []

        merged_aliases = sorted(set(_parse(tgt["aliases"]) + _parse(src["aliases"])))
        merged_tags    = sorted(set(_parse(tgt["source_tags"]) + _parse(src["source_tags"])))

        # Reassign memberships
        c.execute(
            f"UPDATE sanctions_memberships SET canonical_id = {p} WHERE canonical_id = {p}",
            (target_id, source_id),
        )
        # Merge metadata onto target
        c.execute(f"""
            UPDATE vessels_canonical SET
                imo_number  = COALESCE(imo_number,  {p}),
                mmsi        = COALESCE(mmsi,        {p}),
                aliases     = {jp},
                source_tags = {jp},
                updated_at  = {now_expr}
            WHERE canonical_id = {p}
        """, (src["imo_number"], src["mmsi"],
              json.dumps(merged_aliases), json.dumps(merged_tags),
              target_id))
        # Delete source
        c.execute(
            f"DELETE FROM vessels_canonical WHERE canonical_id = {p}",
            (source_id,),
        )


def rebuild_all_source_tags() -> None:
    """
    Recompute source_tags on every vessels_canonical row from its memberships.
    Run after a reconciliation pass to ensure consistency.
    """
    p        = "?" if _BACKEND == "sqlite" else "%s"
    jp       = _jp()
    now_expr = "datetime('now')" if _BACKEND == "sqlite" else "NOW()"

    with _conn() as conn:
        c = _cursor(conn)
        c.execute("SELECT canonical_id FROM vessels_canonical")
        cids = [r["canonical_id"] for r in _rows(c)]

    for cid in cids:
        memberships = get_vessel_memberships(cid)
        tags: list[str] = []
        for m in memberships:
            identifiers = m.get("identifiers") or {}
            new_tags = normalize.parse_source_tags(
                m["list_name"], identifiers
            )
            for t in new_tags:
                if t not in tags:
                    tags.append(t)
        tags.sort()

        with _conn() as conn:
            c = conn.cursor()
            c.execute(f"""
                UPDATE vessels_canonical SET source_tags = {jp}, updated_at = {now_expr}
                WHERE canonical_id = {p}
            """, (json.dumps(tags), cid))
