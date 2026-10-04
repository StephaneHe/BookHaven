"""Scan exclusions: glob patterns relative to BOOKS_ROOT keep files out of the library."""
import os

import config
import scanner


def _write(tmp_path, text):
    p = tmp_path / "scan_exclude.txt"
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_missing_file_means_no_exclusions(tmp_path):
    assert scanner.load_scan_excludes(str(tmp_path / "absent.txt")) == []


def test_comments_and_blank_lines_ignored(tmp_path):
    pats = scanner.load_scan_excludes(_write(tmp_path, "# note\n\n  Comics/X/a.epub  \n"))
    assert pats == [os.path.normcase(os.path.normpath("Comics/X/a.epub"))]


def test_exact_file_excluded_but_siblings_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BOOKS_ROOT", str(tmp_path))
    pats = scanner.load_scan_excludes(_write(tmp_path, "Comics/Série · X/Vol 1.epub\n"))
    d = os.path.join(str(tmp_path), "Comics", "Série · X")
    assert scanner.is_excluded(os.path.join(d, "Vol 1.epub"), pats)
    assert not scanner.is_excluded(os.path.join(d, "Vol 1.cbz"), pats)
    assert not scanner.is_excluded(os.path.join(d, "Vol 2.epub"), pats)


def test_glob_and_case_insensitive_on_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BOOKS_ROOT", str(tmp_path))
    pats = scanner.load_scan_excludes(_write(tmp_path, "comics\\novels\\*.epub\n"))
    p = os.path.join(str(tmp_path), "Comics", "Novels", "a.epub")
    assert scanner.is_excluded(p, pats) == (os.name == "nt")
    assert not scanner.is_excluded(os.path.join(str(tmp_path), "Comics", "Novels", "a.cbz"), pats)


def test_scan_skips_excluded_files(tmp_path, monkeypatch):
    lib = tmp_path / "Comics"
    (lib / "S").mkdir(parents=True)
    (lib / "S" / "novel.epub").write_bytes(b"PK")
    (lib / "S" / "comic.cbz").write_bytes(b"PK")
    monkeypatch.setattr(config, "BOOKS_ROOT", str(tmp_path))
    monkeypatch.setattr(config, "LIBRARY_PATHS", [str(lib)])
    monkeypatch.setattr(config, "SCAN_EXCLUDE_FILE", _write(tmp_path, "Comics/S/novel.epub\n"))
    seen = []
    monkeypatch.setattr(scanner, "_extract_metadata",
                        lambda full_path, *a: seen.append(os.path.basename(full_path)) or (_ for _ in ()).throw(RuntimeError("stop")))

    class FakeConn:
        def execute(self, *a, **k):
            class R:
                def fetchall(self): return []
                def fetchone(self): return None
            return R()
        def commit(self): pass
        def close(self): pass
    monkeypatch.setattr(scanner.database, "get_db", lambda: FakeConn())
    monkeypatch.setattr(scanner, "assign_collections", lambda: 0)
    result = scanner.scan_library()
    assert result["total"] == 1
    assert seen == ["comic.cbz"]
