"""FROZEN copy of the pre-2.3.0 /api/books/grouped implementation.

This is the parity oracle. The body below is a verbatim transcription of
bookhaven.api_books_grouped as it stood at v2.2.0 (bookhaven.py:1642-1819),
with only the request/response plumbing removed so it is a pure function of
(conn, filters, prefix, page, per_page).

DO NOT "improve" this file. Its whole value is that it still behaves like the
old code; the new implementation is compared against it.
"""
from bookhaven import _group_format_variants, _like


def legacy_books_grouped_payload(conn, category="", genre="", author="", fmt="",
                                 search="", prefix="", page=1, per_page=50):
    # Build WHERE clause for filters
    where_parts = []
    params = []
    if category:
        where_parts.append("category = ?")
        params.append(category)
    if genre:
        where_parts.append("genre LIKE ? ESCAPE '\\'")
        params.append(_like(genre))
    if author:
        where_parts.append("author LIKE ? ESCAPE '\\'")
        params.append(_like(author))
    if fmt:
        where_parts.append("format = ?")
        params.append(fmt)
    if search:
        where_parts.append(
            "(title LIKE ? ESCAPE '\\' OR author LIKE ? ESCAPE '\\'"
            " OR series LIKE ? ESCAPE '\\' OR collection_path LIKE ? ESCAPE '\\')")
        params.extend([_like(search)] * 4)

    where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    if prefix:
        # Browsing inside a collection: show next level
        prefix_filter = f'{"AND" if where else "WHERE"} collection_path LIKE ?'
        prefix_param = prefix + '/%'
        exact_filter = f'{"AND" if where else "WHERE"} collection_path = ?'

        all_in_prefix = conn.execute(
            f"SELECT id, title, author, collection_path, has_cover, format, filename, genre FROM books {where} {prefix_filter}",
            params + [prefix_param]
        ).fetchall()

        exact_books = conn.execute(
            f"SELECT * FROM books {where} {exact_filter}",
            params + [prefix]
        ).fetchall()

        # Group by next sub-level
        sub_groups = {}
        for r in all_in_prefix:
            rest = r["collection_path"][len(prefix) + 1:]  # after "prefix/"
            next_level = rest.split("/")[0]
            if next_level not in sub_groups:
                sub_groups[next_level] = {"count": 0, "cover_id": 0, "authors": set(), "full_path": prefix + "/" + next_level}
            sub_groups[next_level]["count"] += 1
            if r["has_cover"] and not sub_groups[next_level]["cover_id"]:
                sub_groups[next_level]["cover_id"] = r["id"]
            sub_groups[next_level]["authors"].add(r["author"])

        collections = []
        for name, info in sorted(sub_groups.items(), key=lambda x: x[0].lower()):
            author_list = sorted(a for a in info["authors"] if a)[:2]
            author_str = ", ".join(author_list)
            if len(info["authors"]) > 2:
                author_str += f" +{len(info['authors'])-2}"
            collections.append({
                "type": "collection",
                "title": name,
                "collection_path": info["full_path"],
                "book_count": info["count"],
                "cover_book_id": info["cover_id"],
                "author": author_str,
            })

        standalone_books = _group_format_variants([dict(r) for r in exact_books])
        for b in standalone_books:
            b["type"] = "book"

        all_items = collections + standalone_books
    else:
        all_books = conn.execute(
            f"SELECT id, title, author, collection_path, has_cover, format, filename, genre FROM books {where}",
            params
        ).fetchall()

        top_groups = {}
        standalone_ids = []

        for r in all_books:
            cp = r["collection_path"]
            if not cp:
                standalone_ids.append(r["id"])
                continue

            top_level = cp.split("/")[0]
            if top_level not in top_groups:
                top_groups[top_level] = {"count": 0, "cover_id": 0, "authors": set(), "has_children": False}
            top_groups[top_level]["count"] += 1
            if "/" in cp:
                top_groups[top_level]["has_children"] = True
            if r["has_cover"] and not top_groups[top_level]["cover_id"]:
                top_groups[top_level]["cover_id"] = r["id"]
            top_groups[top_level]["authors"].add(r["author"])

        collections = []
        single_book_groups = []  # groups with only 1 book and no children -> show as book

        for name, info in top_groups.items():
            if info["count"] == 1 and not info["has_children"]:
                single_book_groups.append(name)
                continue

            author_list = sorted(a for a in info["authors"] if a)[:2]
            author_str = ", ".join(author_list)
            if len(info["authors"]) > 2:
                author_str += f" +{len(info['authors'])-2}"
            collections.append({
                "type": "collection",
                "title": name,
                "collection_path": name,
                "book_count": info["count"],
                "cover_book_id": info["cover_id"],
                "author": author_str,
            })

        if standalone_ids or single_book_groups:
            extra_where = []
            extra_params = list(params)
            if standalone_ids:
                extra_where.append(f"id IN ({','.join('?' * len(standalone_ids))})")
                extra_params.extend(standalone_ids)
            if single_book_groups:
                extra_where.append(f"collection_path IN ({','.join('?' * len(single_book_groups))})")
                extra_params.extend(single_book_groups)

            combined = " OR ".join(extra_where)
            base_where = f"WHERE ({combined})" if not where else f"{where} AND ({combined})"
            standalone_rows = conn.execute(
                f"SELECT * FROM books {base_where}", extra_params
            ).fetchall()
        else:
            standalone_rows = []

        standalone_books = _group_format_variants([dict(r) for r in standalone_rows])
        for b in standalone_books:
            b["type"] = "book"

        all_items = collections + standalone_books

    # Sort
    all_items.sort(key=lambda x: (x.get("title") or "").lower())

    total = len(all_items)
    start = (page - 1) * per_page
    page_items = all_items[start:start + per_page]

    return {
        "items": page_items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "prefix": prefix,
    }
