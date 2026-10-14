"""SPE camera files: LightField 3.0 (XML footer, per-frame metadata, ROIs) and WinView 2.x headers."""
from __future__ import annotations

import struct

import numpy as np
import pytest

from masksim.spe import HEADER_SIZE, WINVIEW_ID, SpeError, read_spe, write_spe


def _frames(n=3, h=5, w=7, dtype=np.uint16):
    rng = np.random.default_rng(1)
    return rng.integers(0, 60000, size=(n, h, w)).astype(dtype)


def _v2_file(frames: np.ndarray, code: int, *, declared=None, rois=(), ver=2.5, exposure=0.25) -> bytes:
    n, h, w = frames.shape
    header = bytearray(HEADER_SIZE)
    struct.pack_into("<HHf", header, 6, 1340, 0, exposure)  # xDimDet, mode, exp_sec
    struct.pack_into("<H", header, 18, 1300)  # yDimDet
    header[20:29] = b"02Jul2018"
    header[172:178] = b"094615"
    struct.pack_into("<f", header, 36, -70.0)
    struct.pack_into("<H", header, 42, w)
    struct.pack_into("<h", header, 108, code)
    header[200:213] = b"first comment"
    struct.pack_into("<H", header, 600, 0b101)  # rotate, flip
    struct.pack_into("<H", header, 656, h)
    struct.pack_into("<i", header, 1446, n if declared is None else declared)
    struct.pack_into("<h", header, 1510, len(rois))
    for i, roi in enumerate(rois):
        struct.pack_into("<6H", header, 1512 + 12 * i, *roi)
    struct.pack_into("<f", header, 1992, ver)
    struct.pack_into("<i", header, 2996, WINVIEW_ID)
    return bytes(header) + np.ascontiguousarray(frames).tobytes()


def test_v3_round_trip_keeps_pixels_metadata_and_sensor_mapping():
    frames = _frames()
    spe = read_spe(write_spe(frames, exposure_s=0.05, sensor_origin=(100, 40), binning=(2, 4),
                             sensor_size=(2048, 2048), timestamps_s=[0.0, 0.5, 1.25], temperature_c=-60))
    assert spe.version == 3.0 and spe.n_frames == 3 and spe.dtype == np.uint16
    (region,) = spe.regions
    np.testing.assert_array_equal(region.data, frames)  # frames are 16 bytes of metadata apart
    assert (region.x, region.y, region.x_binning, region.y_binning) == (100, 40, 2, 4)
    xs, ys = region.pixel_axes()
    assert xs[0] == 100.5 and xs[1] == 102.5 and ys[0] == 41.5  # centres of 2x4 binned pixels
    assert spe.sensor == (2048, 2048)
    np.testing.assert_allclose(spe.timestamps["ExposureStarted"], [0.0, 0.5, 1.25])
    np.testing.assert_array_equal(spe.frame_numbers, [1, 2, 3])
    assert spe.summary["exposure_s"] == pytest.approx(0.05)
    assert spe.summary["temperature_c"] == -60
    assert ("DataHistories/DataHistory/Origin@software", "masksim.spe") in spe.settings
    assert not spe.warnings


@pytest.mark.parametrize("dtype", [np.uint16, np.uint32, np.float32, np.int32])
def test_v3_pixel_formats(dtype):
    frames = _frames(dtype=dtype)
    spe = read_spe(write_spe(frames))
    assert spe.dtype == dtype
    np.testing.assert_array_equal(spe.regions[0].data, frames)


def test_v3_regions_and_unaligned_metadata():
    """Two ROIs per frame, then 3 metadata bytes LightField didn't describe (copied, not viewed)."""
    a, b = _frames(2, 3, 4), _frames(2, 2, 5) + 7
    size = a[0].nbytes + b[0].nbytes
    body = b"".join(a[i].tobytes() + b[i].tobytes() + b"xyz" for i in range(2))
    xml = (
        '<SpeFormat version="3.0" xmlns="http://www.princetoninstruments.com/spe/2009"><DataFormat>'
        f'<DataBlock type="Frame" count="2" pixelFormat="MonochromeUnsigned16" size="{size}" stride="{size + 3}">'
        f'<DataBlock type="Region" pixelFormat="MonochromeUnsigned16" size="{a[0].nbytes}" stride="{a[0].nbytes}" '
        'calibrations="1" width="4" height="3"/>'
        f'<DataBlock type="Region" pixelFormat="MonochromeUnsigned16" size="{b[0].nbytes}" stride="{b[0].nbytes}" '
        'calibrations="2" width="5" height="2"/></DataBlock></DataFormat><Calibrations>'
        '<SensorMapping id="1" x="0" y="0" width="4" height="3" xBinning="1" yBinning="1"/>'
        '<SensorMapping id="2" x="10" y="20" width="5" height="2" xBinning="1" yBinning="1"/>'
        '</Calibrations></SpeFormat>'
    ).encode()
    header = bytearray(HEADER_SIZE)
    struct.pack_into("<Q", header, 678, HEADER_SIZE + len(body))
    struct.pack_into("<f", header, 1992, 3.0)
    struct.pack_into("<H", header, 4098, 0x5555)
    spe = read_spe(bytes(header) + body + xml)
    np.testing.assert_array_equal(spe.regions[0].data, a)
    np.testing.assert_array_equal(spe.regions[1].data, b)
    assert (spe.regions[1].x, spe.regions[1].y) == (10, 20)
    assert spe.warnings == ["3 bytes of per-frame metadata were not decoded"]


@pytest.mark.parametrize(("code", "dtype"), [(0, np.float32), (1, np.int32), (2, np.int16), (3, np.uint16),
                                              (8, np.uint32)])
def test_v2_header_layout(code, dtype):
    frames = _frames(dtype=dtype)
    spe = read_spe(_v2_file(frames, code, rois=[(11, 17, 1, 21, 25, 1)]))
    assert spe.version == 2.5 and spe.dtype == dtype and spe.n_frames == 3
    (region,) = spe.regions
    np.testing.assert_array_equal(region.data, frames)
    assert (region.x, region.y) == (10, 20)  # WinView ROIs are 1-based
    assert spe.sensor == (1340, 1300)
    assert spe.summary["created"] == "2018-07-02T09:46:15"
    assert spe.summary["exposure_s"] == 0.25 and spe.summary["temperature_c"] == -70
    assert spe.summary["geometric"] == "rotate, flip"
    assert spe.summary["comments"] == "first comment"


def test_v2_multiple_rois_split_each_frame():
    a, b = _frames(2, 2, 3), _frames(2, 1, 4) + 1
    body = b"".join(a[i].tobytes() + b[i].tobytes() for i in range(2))
    # The header's frame size is the concatenation: 10 pixels as 10 x 1.
    raw = bytearray(_v2_file(np.zeros((2, 1, 10), np.uint16), 3, rois=[(1, 3, 1, 1, 2, 1), (5, 8, 1, 9, 9, 1)]))
    raw[HEADER_SIZE:] = body
    spe = read_spe(bytes(raw))
    np.testing.assert_array_equal(spe.regions[0].data, a)
    np.testing.assert_array_equal(spe.regions[1].data, b)
    assert (spe.regions[1].x, spe.regions[1].y) == (4, 8)


def test_wrong_frame_count_is_clamped_to_the_data():
    frames = _frames(n=2)
    spe = read_spe(_v2_file(frames, 3, declared=5))
    assert spe.n_frames == 2
    assert spe.warnings == ["the header declares 5 frames, but the file holds 2"]
    np.testing.assert_array_equal(spe.regions[0].data, frames)


def test_unreadable_files_raise():
    with pytest.raises(SpeError, match="too short"):
        read_spe(b"\0" * 100)
    with pytest.raises(SpeError, match="not an SPE file"):
        read_spe(b"\0" * 5000)
    good = bytearray(write_spe(_frames()))
    xml_at = struct.unpack_from("<Q", good, 678)[0]
    evil = bytes(good[:xml_at]) + b'<!DOCTYPE x [<!ENTITY a "aaaa">]><SpeFormat/>'
    with pytest.raises(SpeError, match="DTD"):
        read_spe(evil)
    with pytest.raises(SpeError, match="no complete frame"):
        read_spe(_v2_file(np.zeros((1, 4, 4), np.uint16), 3)[:HEADER_SIZE + 10])


def test_reads_paths(tmp_path):
    frames = _frames()
    path = tmp_path / "image.spe"
    path.write_bytes(write_spe(frames))
    np.testing.assert_array_equal(read_spe(path).regions[0].data, frames)
