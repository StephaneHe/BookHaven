"""Payload comparison helpers for the /api/books/grouped parity tests.

`normalize` erases the three deliberate divergences between the pre-2.3.0
implementation and the SQL-backed one -- and nothing else. Every other
difference, list order included, must make the comparison fail.
"""
import json

import bookhaven


def jsonable(payload):
    """Round-trip through JSON so Row-derived values compare like the API's."""
    return json.loads(json.dumps(payload))


def _tie_key(item):
    """Canonical order inside a run of items whose title.lower() is equal."""
    return (item["type"], item.get("collection_path") or "", item.get("id") or 0)


def normalize(payload):
    """Erase the divergences the plan allows, and only those.

    1. cover_book_id of a collection: the legacy value was whichever covered
       row the query plan returned first; the new one is MIN(id). Compared
       here as "has a cover or not" -- the exact value is pinned by
       test_books_grouped_agg.py.
    2. Order of items that tie on title.lower(): the legacy order came from a
       dict's insertion order. Both sides are re-sorted on a canonical key.
    3. Order of variants that tie on FORMAT_PRIORITY inside `formats` (same
       base filename AND same format, e.g. two "top.epub" in different
       folders): the legacy sort was stable over whatever order the query plan
       returned; the new one orders by id. Both sides are re-sorted by
       (priority, id), so the priority order -- and therefore which variant is
       the primary -- stays strictly compared.
    """
    payload = jsonable(payload)
    for item in payload["items"]:
        if item["type"] == "collection":
            item["cover_book_id"] = bool(item["cover_book_id"])
        else:
            item["formats"] = sorted(
                item["formats"],
                key=lambda f: (bookhaven.FORMAT_PRIORITY.get(f["format"], 9), f["id"]))

    items, out = payload["items"], []
    i = 0
    while i < len(items):
        j = i
        key = (items[i].get("title") or "").lower()
        while j < len(items) and (items[j].get("title") or "").lower() == key:
            j += 1
        out.extend(sorted(items[i:j], key=_tie_key))
        i = j
    payload["items"] = out
    return payload


def diff_payloads(new, old):
    """Human-readable differences after normalisation; [] when identical."""
    a, b = normalize(new), normalize(old)
    if a == b:
        return []
    out = []
    for key in ("total", "pages", "page", "per_page", "prefix"):
        if a.get(key) != b.get(key):
            out.append(f"{key}: new={a.get(key)!r} old={b.get(key)!r}")
    if len(a["items"]) != len(b["items"]):
        out.append(f"item count: new={len(a['items'])} old={len(b['items'])}")
    for idx, (x, y) in enumerate(zip(a["items"], b["items"])):
        if x != y:
            fields = sorted(k for k in set(x) | set(y) if x.get(k) != y.get(k))
            out.append(f"item #{idx} ({x.get('title')!r} vs {y.get('title')!r}): "
                       + ", ".join(f"{k}: new={x.get(k)!r} old={y.get(k)!r}"
                                   for k in fields))
    return out
