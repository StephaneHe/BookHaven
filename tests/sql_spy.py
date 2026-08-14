"""A sqlite3 connection proxy that records the SQL run and the rows fetched.

sqlite3.Connection attributes are read-only, so the endpoint's connection
cannot be monkeypatched in place -- it has to be wrapped.
"""


class SpyCursor:
    def __init__(self, cursor, record):
        self._cursor = cursor
        self._record = record

    def _count(self, rows):
        self._record["rows"] += len(rows)
        return rows

    def fetchall(self):
        return self._count(self._cursor.fetchall())

    def fetchmany(self, *a):
        return self._count(self._cursor.fetchmany(*a))

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is not None:
            self._record["rows"] += 1
        return row

    def __iter__(self):
        for row in self._cursor:
            self._record["rows"] += 1
            yield row

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class SpyConnection:
    """Wraps a real connection; `queries` collects {sql, params, rows}."""

    def __init__(self, conn):
        self._conn = conn
        self.queries = []

    def execute(self, sql, params=()):
        record = {"sql": " ".join(sql.split()), "params": params, "rows": 0}
        self.queries.append(record)
        return SpyCursor(self._conn.execute(sql, params), record)

    def executescript(self, sql):
        return self._conn.executescript(sql)

    def close(self):
        return self._conn.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)

    # -- helpers for the assertions -------------------------------------
    def total_rows(self):
        return sum(q["rows"] for q in self.queries)

    def select_star_queries(self):
        return [q for q in self.queries if "SELECT * FROM books" in q["sql"]]

    def book_queries(self):
        return [q for q in self.queries if "FROM books" in q["sql"]]
