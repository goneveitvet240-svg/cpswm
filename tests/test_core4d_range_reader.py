import io
import zipfile

import pytest

from tools.fetch_core4d_development_subset import ConcatRangeReader


def reader(tmp_path, payload, *, budget=100000, fetch_override=None):
    chunks = [payload[:19], payload[19:]]
    parts = [dict(url=str(i), size=len(b)) for i, b in enumerate(chunks)]

    def fetch(part, start, end):
        return chunks[int(part["url"])][start:end]

    return ConcatRangeReader(parts, tmp_path, budget=budget, fetch=fetch_override or fetch)


def test_zip_member_crosses_parts_and_cached_replay(tmp_path):
    wire = io.BytesIO()
    with zipfile.ZipFile(wire, "w") as z:
        z.writestr("video", b"raw-video-pixels" * 100)
    r = reader(tmp_path, wire.getvalue())
    with zipfile.ZipFile(r) as z:
        assert z.read("video") == b"raw-video-pixels" * 100
    assert r.downloaded == len(wire.getvalue())
    r = reader(
        tmp_path, wire.getvalue(), fetch_override=lambda *_: pytest.fail("network on cache hit")
    )
    with zipfile.ZipFile(r) as z:
        assert z.read("video") == b"raw-video-pixels" * 100
    assert r.downloaded == 0


def test_budget_and_corrupted_cache_rejected(tmp_path):
    r = reader(tmp_path, b"x" * 100, budget=20)
    with pytest.raises(ValueError, match="budget"):
        r.read(100)
    cache = next(tmp_path.glob("*.bin"))
    cache.write_bytes(b"changed")
    r = reader(tmp_path, b"x" * 100)
    with pytest.raises(ValueError, match="changed"):
        r.read(10)


def test_short_response_rejected(tmp_path):
    r = reader(tmp_path, b"x" * 100, fetch_override=lambda *_: b"x")
    with pytest.raises(ValueError, match="short"):
        r.read(5)


def test_cache_identity_and_unbounded_read_rejected(tmp_path):
    reader(tmp_path, b"x" * 100)
    with pytest.raises(ValueError, match="identity"):
        reader(tmp_path, b"x" * 101)
    r = ConcatRangeReader(
        [dict(url="large", size=100 * 1024 * 1024)],
        tmp_path / "large",
        fetch=lambda *_: pytest.fail("must not fetch"),
    )
    with pytest.raises(ValueError, match="allocation"):
        r.read()


def test_resume_metadata_cannot_overwrite_changed_selection(tmp_path):
    from tools.fetch_core4d_development_subset import retain_text

    path = tmp_path / "selection.json"
    retain_text(path, "same")
    retain_text(path, "same")
    with pytest.raises(ValueError, match="metadata differs"):
        retain_text(path, "changed")
    assert path.read_text() == "same"
