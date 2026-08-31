"""Media intermediates stay beside their destination and are cleaned on failure."""
from pathlib import Path

import pytest
from PIL import Image

import aeroforge.tools.windtunnel_viz as viz


def test_mp4_intermediate_stays_in_output_directory(tmp_path, monkeypatch):
    cv2 = pytest.importorskip("cv2")
    frame = tmp_path / "frame.png"
    Image.new("RGB", (160, 90), (40, 60, 80)).save(frame)
    destination = tmp_path / "输出" / "animation.mp4"
    original = cv2.VideoWriter
    locations = []

    def capture_writer(filename, *args, **kwargs):
        locations.append(Path(filename).resolve())
        return original(filename, *args, **kwargs)

    monkeypatch.setattr(cv2, "VideoWriter", capture_writer)
    assert viz._encode_mp4([frame, frame], destination, 2) == destination
    assert locations and all(p.parent == destination.parent.resolve() for p in locations)
    assert list(destination.parent.iterdir()) == [destination]


def test_mp4_failure_removes_only_its_intermediate(tmp_path, monkeypatch):
    cv2 = pytest.importorskip("cv2")
    frame = tmp_path / "frame.png"
    Image.new("RGB", (160, 90), (40, 60, 80)).save(frame)
    destination = tmp_path / "output" / "animation.mp4"
    destination.parent.mkdir()
    keep = destination.parent / "keep.txt"
    keep.write_text("user data")
    locations = []

    class BrokenWriter:
        def __init__(self, filename, *_args):
            self.path = Path(filename).resolve()
            locations.append(self.path)
            self.path.write_bytes(b"partial")

        def isOpened(self):
            return True

        def write(self, _frame):
            raise RuntimeError("encoder failed")

        def release(self):
            pass

    monkeypatch.setattr(cv2, "VideoWriter", BrokenWriter)
    with pytest.raises(RuntimeError, match="encoder failed"):
        viz._encode_mp4([frame], destination, 2)
    assert all(not path.exists() for path in locations)
    assert list(destination.parent.iterdir()) == [keep]
