"""docs/USER_REQUIREMENTS.md stays honest: every requirement row names at least
one automated test that really exists, or is explicitly marked MANUEL with a
reason (device-only behaviour). A renamed or deleted test fails here.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "docs", "USER_REQUIREMENTS.md")

ROW = re.compile(r"^\|\s*(R\d{2,3})\s*\|(.*)\|\s*$")
REF = re.compile(r"`([^`]+?)::([A-Za-z0-9_`\- ]+?)`")


def _rows():
    rows = []
    with open(DOC, encoding="utf-8") as f:
        for line in f:
            m = ROW.match(line.rstrip("\n"))
            if m:
                rows.append((m.group(1), line))
    return rows


def _test_exists(path, name):
    full = os.path.join(ROOT, path.replace("/", os.sep))
    if not os.path.isfile(full):
        return False
    src = open(full, encoding="utf-8").read()
    name = name.strip("` ")
    if path.endswith(".py"):
        return re.search(rf"^\s*def {re.escape(name)}\(", src, re.M) is not None
    # Kotlin: fun name( or fun `name`(
    return re.search(rf"fun\s+`?{re.escape(name)}`?\s*\(", src) is not None


def test_registry_exists_and_lists_requirements():
    rows = _rows()
    assert len(rows) >= 50, "docs/USER_REQUIREMENTS.md should list every delivered user requirement"
    ids = [r for r, _ in rows]
    assert len(ids) == len(set(ids)), "duplicate requirement ids"


def test_every_requirement_is_protected_by_an_existing_test():
    problems = []
    for rid, line in _rows():
        refs = REF.findall(line)
        if not refs:
            if "MANUEL" not in line:
                problems.append(f"{rid}: no automated test and not marked MANUEL")
            continue
        for path, name in refs:
            if not _test_exists(path, name):
                problems.append(f"{rid}: missing test {path}::{name}")
    assert not problems, "\n".join(problems)
