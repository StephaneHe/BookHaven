"""Comic pages sort naturally: unpadded numbers ("chap_2", "chap_10") stay in reading order."""
import zipfile

import bookhaven
import scanner


def test_natural_key_orders_numbers_numerically():
    names = ["chap_10_p_0.jpg", "chap_2_p_10.jpg", "chap_2_p_2.jpg", "chap_1.jpg", "Chap_2_p_1.jpg"]
    assert sorted(names, key=scanner.natural_key) == [
        "chap_1.jpg", "Chap_2_p_1.jpg", "chap_2_p_2.jpg", "chap_2_p_10.jpg", "chap_10_p_0.jpg"]


def test_zero_padded_names_keep_their_order():
    names = [f"Series 001 - {i:02d}.jpg" for i in range(1, 25)]
    assert sorted(names, key=scanner.natural_key) == sorted(names)


def test_list_comic_pages_is_natural(tmp_path):
    p = tmp_path / "t.cbz"
    with zipfile.ZipFile(p, "w") as z:
        for n in ["p_10.jpg", "p_2.jpg", "p_1.jpg", "notes.txt"]:
            z.writestr(n, b"x")
    assert bookhaven._list_comic_pages(str(p), "cbz") == ["p_1.jpg", "p_2.jpg", "p_10.jpg"]
