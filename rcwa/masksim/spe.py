"""Princeton Instruments / Teledyne SPE camera files (WinView/WinSpec 2.x and LightField 3.0).

Layout (Princeton Instruments, "SPE 3.0 File Format Specification"):

- A 4100-byte little-endian binary header. The fields every version fills are the pixel
  data type (offset 108), the frame width and height (42, 656), the frame count (1446),
  and the header version (1992). 2.x files keep their acquisition settings here too.
  The header ends with the value 0x5555 at offset 4098; old WinView files leave that 0
  but carry the id 0x01234567 at offset 2996.
- Pixel data from offset 4100, frame after frame, rows of `width` pixels.
- Version 3.0 appends an XML footer at the 64-bit offset stored at 678. Its `DataFormat`
  element is authoritative for the layout: frames may hold several regions of interest,
  and each frame can be followed by per-frame metadata (time stamps, frame tracking
  numbers), so the frame `stride` can exceed its `size`. The rest of the XML records the
  sensor mapping (region position and binning) and every acquisition setting.

Some acquisition software writes a wrong frame count, so it is clamped to the data that
is actually present (with a warning), as imageio does.
"""
from __future__ import annotations

import re
import struct
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

HEADER_SIZE = 4100
LAST_VALUE = 0x5555  # int16 at offset 4098 of valid headers (old WinView files leave it 0)
WINVIEW_ID = 0x01234567  # int32 at offset 2996 of WinView/WinSpec headers

# Header data type codes (offset 108). 5 (float64) and 6 (uint8) come from WinView's own docs.
_HEADER_DTYPES = {0: "<f4", 1: "<i4", 2: "<i2", 3: "<u2", 5: "<f8", 6: "u1", 8: "<u4"}
_HEADER_CODES = {np.dtype(v): k for k, v in _HEADER_DTYPES.items()}
_XML_DTYPES = {("Unsigned", 8): "u1", ("Unsigned", 16): "<u2", ("Unsigned", 32): "<u4",
               ("Signed", 16): "<i2", ("Signed", 32): "<i4", ("Floating", 32): "<f4", ("Floating", 64): "<f8"}
_GEOMETRIC = ("rotate", "reverse", "flip")
XML_NS = "http://www.princetoninstruments.com/spe/2009"


class SpeError(ValueError):
    """The bytes are not a readable SPE file."""


@dataclass(frozen=True, eq=False)
class SpeRegion:
    """One region of interest: `data` is (frames, height, width), rows as read out.

    `x`, `y` locate the region's first pixel on the sensor (0-based sensor pixels) and
    `x_binning`, `y_binning` say how many sensor pixels each data pixel sums.
    """

    data: np.ndarray
    x: int = 0
    y: int = 0
    x_binning: int = 1
    y_binning: int = 1

    @property
    def width(self) -> int:
        return self.data.shape[2]

    @property
    def height(self) -> int:
        return self.data.shape[1]

    def pixel_axes(self) -> Tuple[np.ndarray, np.ndarray]:
        """Centres of the data pixels in sensor pixel coordinates (x along a row, y down)."""
        xs = self.x + (np.arange(self.width) + 0.5) * self.x_binning - 0.5
        ys = self.y + (np.arange(self.height) + 0.5) * self.y_binning - 0.5
        return xs, ys


@dataclass(frozen=True, eq=False)
class SpeFile:
    version: float
    dtype: np.dtype
    n_frames: int
    regions: Tuple[SpeRegion, ...]
    sensor: Optional[Tuple[int, int]] = None  # (width, height) in pixels, when the file says
    summary: Dict[str, object] = field(default_factory=dict)  # well-known settings, see _summary_*
    settings: List[Tuple[str, str]] = field(default_factory=list)  # every setting as (path, value)
    timestamps: Dict[str, np.ndarray] = field(default_factory=dict)  # event -> seconds per frame
    frame_numbers: Optional[np.ndarray] = None
    xml: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    @property
    def nbytes(self) -> int:
        return sum(r.data.nbytes for r in self.regions)


def read_spe(source: Union[str, Path, bytes, bytearray, memoryview]) -> SpeFile:
    """Read an SPE file from a path or from its bytes (arrays are views of those bytes)."""
    buffer = Path(source).read_bytes() if isinstance(source, (str, Path)) else source
    raw = memoryview(buffer).cast("B")
    if len(raw) < HEADER_SIZE:
        raise SpeError(f"too short for an SPE file ({len(raw)} bytes; the header alone has {HEADER_SIZE})")
    header = bytes(raw[:HEADER_SIZE])
    if _unpack(header, 4098, "<H") != LAST_VALUE and _unpack(header, 2996, "<i") != WINVIEW_ID:
        raise SpeError("not an SPE file (the header has neither the 0x5555 end mark nor the WinView id)")
    version = round(float(_unpack(header, 1992, "<f")), 3)
    xml_offset = _unpack(header, 678, "<Q") if version >= 3 else 0

    if version >= 3 and HEADER_SIZE <= xml_offset <= len(raw):
        xml_bytes = bytes(raw[xml_offset:])
        # SPE footers never declare a DTD; refusing one rules out entity expansion attacks.
        if b"<!DOCTYPE" in xml_bytes or b"<!ENTITY" in xml_bytes:
            raise SpeError("the XML footer declares a DTD, which SPE files never do")
        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError as exc:
            raise SpeError(f"unreadable XML footer: {exc}") from None
        return _read_v3(raw, header, version, xml_offset, root, xml_bytes.decode("utf-8", "replace").lstrip("﻿"))
    return _read_v2(raw, header, version)


# ---- version 3.0 (LightField) -------------------------------------------------------------


def _read_v3(raw: memoryview, header: bytes, version: float, data_end: int, root: ET.Element, xml: str) -> SpeFile:
    _strip_namespaces(root)
    frame_block = root.find("DataFormat/DataBlock[@type='Frame']")
    if frame_block is None:
        raise SpeError("the XML footer has no DataFormat frame block")
    dtype = _xml_dtype(frame_block.get("pixelFormat", ""))
    declared = _int_attr(frame_block, "count")
    frame_size = _int_attr(frame_block, "size")
    frame_stride = _int_attr(frame_block, "stride", frame_size)
    region_blocks = frame_block.findall("DataBlock[@type='Region']")
    if not region_blocks:
        raise SpeError("the XML frame block lists no regions")

    warnings: List[str] = []
    n_frames = _clamp_frames(declared, frame_size, frame_stride, data_end - HEADER_SIZE, warnings)
    calibrations = root.find("Calibrations")
    sensor_info = calibrations.find("SensorInformation") if calibrations is not None else None
    sensor = ((_int_attr(sensor_info, "width"), _int_attr(sensor_info, "height"))
              if sensor_info is not None and sensor_info.get("width") else None)

    regions = []
    offset = HEADER_SIZE
    for block in region_blocks:
        width, height = _int_attr(block, "width"), _int_attr(block, "height")
        region_dtype = _xml_dtype(block.get("pixelFormat", "")) if block.get("pixelFormat") else dtype
        size = _int_attr(block, "size", width * height * region_dtype.itemsize)
        if width * height * region_dtype.itemsize != size:
            raise SpeError(f"region size {size} B does not match {width} x {height} {region_dtype.name} pixels")
        data = _frames_view(raw, offset, n_frames, frame_stride, height, width, region_dtype)
        mapping = _sensor_mapping(calibrations, block.get("calibrations", ""))
        regions.append(SpeRegion(data, *mapping))
        offset += _int_attr(block, "stride", size)
    if offset - HEADER_SIZE > frame_size:
        raise SpeError(f"the regions ({offset - HEADER_SIZE} B) overflow the frame size ({frame_size} B)")

    timestamps, frame_numbers = _frame_metadata(raw, root, n_frames, frame_size, frame_stride, warnings)
    settings = _flatten_settings(root)
    return SpeFile(
        version=version, dtype=regions[0].data.dtype, n_frames=n_frames, regions=tuple(regions), sensor=sensor,
        summary=_summary_v3(root, settings, header), settings=settings, timestamps=timestamps,
        frame_numbers=frame_numbers, xml=xml, warnings=warnings,
    )


def _strip_namespaces(root: ET.Element) -> None:
    for element in root.iter():
        if isinstance(element.tag, str) and "}" in element.tag:
            element.tag = element.tag.split("}", 1)[1]
        for key in [k for k in element.attrib if "}" in k]:
            element.attrib[key.split("}", 1)[1]] = element.attrib.pop(key)


def _xml_dtype(pixel_format: str) -> np.dtype:
    match = re.fullmatch(r"Monochrome(Unsigned|Signed|Floating)(\d+)", pixel_format)
    key = (match.group(1), int(match.group(2))) if match else None
    if key not in _XML_DTYPES:
        raise SpeError(f"unsupported pixel format {pixel_format!r}")
    return np.dtype(_XML_DTYPES[key])


def _int_attr(element: ET.Element, name: str, default: Optional[int] = None) -> int:
    value = element.get(name)
    if value is None:
        if default is None:
            raise SpeError(f"<{element.tag}> lacks the {name!r} attribute")
        return default
    try:
        return int(value)
    except ValueError:
        raise SpeError(f"<{element.tag} {name}={value!r}> is not an integer") from None


def _sensor_mapping(calibrations: Optional[ET.Element], ids: str) -> Tuple[int, int, int, int]:
    """(x, y, x_binning, y_binning) of the region from its SensorMapping calibration."""
    if calibrations is not None:
        wanted = {i.strip() for i in ids.split(",") if i.strip()}
        for mapping in calibrations.iter("SensorMapping"):
            if not wanted or mapping.get("id") in wanted:
                return (_int_attr(mapping, "x", 0), _int_attr(mapping, "y", 0),
                        max(_int_attr(mapping, "xBinning", 1), 1), max(_int_attr(mapping, "yBinning", 1), 1))
    return 0, 0, 1, 1


def _frame_metadata(raw: memoryview, root: ET.Element, n_frames: int, frame_size: int, frame_stride: int,
                    warnings: List[str]) -> Tuple[Dict[str, np.ndarray], Optional[np.ndarray]]:
    """Per-frame time stamps (seconds) and frame tracking numbers stored after each frame."""
    blocks = root.findall("MetaFormat/MetaBlock")
    widths = [_int_attr(b, "bitDepth", 64) // 8 for b in blocks]
    if not blocks or sum(widths) != frame_stride - frame_size:
        if frame_stride > frame_size:
            warnings.append(f"{frame_stride - frame_size} bytes of per-frame metadata were not decoded")
        return {}, None
    timestamps: Dict[str, np.ndarray] = {}
    frame_numbers = None
    offset = frame_size
    for block, width in zip(blocks, widths, strict=True):
        kind = block.get("type", "")
        if width == 8 and kind in ("TimeStamp", "FrameTrackingNumber"):
            values = _frames_view(raw, HEADER_SIZE + offset, n_frames, frame_stride, 1, 1, np.dtype("<i8"))
            values = values.reshape(n_frames).copy()
            if kind == "TimeStamp":
                resolution = float(block.get("resolution") or 1)
                timestamps[block.get("event") or f"TimeStamp{len(timestamps)}"] = values / resolution
            else:
                frame_numbers = values
        offset += width
    return timestamps, frame_numbers


def _flatten_settings(root: ET.Element) -> List[Tuple[str, str]]:
    """Every leaf of the XML outside DataFormat/MetaFormat as ("A/B/C", text) rows.

    Attributes become "A/B@name" rows, so nothing the camera software saved is hidden.
    """
    rows: List[Tuple[str, str]] = []

    def walk(element: ET.Element, path: str) -> None:
        for key, value in element.attrib.items():
            rows.append((f"{path}@{key}", value))
        children = list(element)
        text = (element.text or "").strip()
        if not children and text:
            rows.append((path, text))
        for child in children:
            if isinstance(child.tag, str):
                walk(child, f"{path}/{child.tag}")

    for child in root:
        if isinstance(child.tag, str) and child.tag not in ("DataFormat", "MetaFormat"):
            walk(child, child.tag)
    return rows


def _first(settings: Sequence[Tuple[str, str]], pattern: str) -> Optional[str]:
    rx = re.compile(pattern)
    return next((value for path, value in settings if rx.search(path)), None)


def _number(text: Optional[str]) -> Optional[float]:
    try:
        return float(text) if text is not None else None
    except ValueError:
        return None


def _summary_v3(root: ET.Element, settings: List[Tuple[str, str]], header: bytes) -> Dict[str, object]:
    """Commonly needed acquisition settings, looked up by element name wherever LightField put them."""
    camera = next(root.iter("Camera"), None)
    exposure_ms = _number(_first(settings, r"/ShutterTiming/ExposureTime$"))
    summary: Dict[str, object] = {
        "software": "LightField",
        "created": _first(settings, r"(FileInformation|Origin)@created$"),
        "camera": " ".join(filter(None, (camera.get("model"), camera.get("serialNumber")))) if camera is not None
        else None,
        "exposure_s": exposure_ms / 1e3 if exposure_ms is not None else _header_float(header, 10),
        "temperature_set_c": _number(_first(settings, r"/Temperature/SetPoint$")),
        "temperature_c": _number(_first(settings, r"/Temperature/Reading$")),
        "adc_speed_mhz": _number(_first(settings, r"/Adc/Speed$")),
        "adc_gain": _first(settings, r"/Adc/(AnalogGain|Gain)$"),
        "adc_quality": _first(settings, r"/Adc/Quality$"),
        "em_gain": _number(_first(settings, r"/Adc/ElectronMultiplicationGain$")),
        "readout": _first(settings, r"/ReadoutControl/Mode$"),
        "accumulations": _number(_first(settings, r"/Accumulations$")),
    }
    return {k: v for k, v in summary.items() if v not in (None, "")}


# ---- versions 1.x-2.x (WinView / WinSpec) ---------------------------------------------------------


def _read_v2(raw: memoryview, header: bytes, version: float) -> SpeFile:
    code = _unpack(header, 108, "<h")
    if code not in _HEADER_DTYPES:
        raise SpeError(f"unknown pixel data type code {code}")
    dtype = np.dtype(_HEADER_DTYPES[code])
    width, height = _unpack(header, 42, "<H"), _unpack(header, 656, "<H")
    if not width or not height:
        raise SpeError(f"frame size {width} x {height} in the header")
    declared = _unpack(header, 1446, "<i")

    rois = [struct.unpack_from("<6H", header, 1512 + 12 * i) for i in range(10)]
    n_roi = _unpack(header, 1510, "<h")
    shapes: List[Tuple[int, int, int, int, int, int]] = []  # (width, height, x, y, x_bin, y_bin)
    if n_roi > 1:
        for startx, endx, groupx, starty, endy, groupy in rois[:n_roi]:
            gx, gy = max(groupx, 1), max(groupy, 1)
            shapes.append(((endx - startx + 1) // gx, (endy - starty + 1) // gy, max(startx - 1, 0),
                           max(starty - 1, 0), gx, gy))
        if sum(w * h for w, h, *_ in shapes) != width * height:
            shapes = []  # inconsistent ROI table: fall back to one region of the header size
    if not shapes:
        startx, endx, groupx, starty, endy, groupy = rois[0]
        gx, gy = max(groupx, 1), max(groupy, 1)
        fits = startx >= 1 and (endx - startx + 1) // gx == width and (endy - starty + 1) // gy == height
        shapes = [(width, height, startx - 1, starty - 1, gx, gy) if fits else (width, height, 0, 0, 1, 1)]

    frame_size = width * height * dtype.itemsize
    warnings: List[str] = []
    n_frames = _clamp_frames(declared, frame_size, frame_size, len(raw) - HEADER_SIZE, warnings)
    regions = []
    offset = HEADER_SIZE
    for w, h, x, y, gx, gy in shapes:
        regions.append(SpeRegion(_frames_view(raw, offset, n_frames, frame_size, h, w, dtype), x, y, gx, gy))
        offset += w * h * dtype.itemsize

    det = (_unpack(header, 6, "<H"), _unpack(header, 18, "<H"))
    flags = _unpack(header, 600, "<H")
    comments = [_text(header, 200 + 80 * i, 80) for i in range(5)]
    summary: Dict[str, object] = {
        "software": "WinView/WinSpec",
        "created": _datetime_v2(_text(header, 20, 10), _text(header, 172, 7)),
        "exposure_s": _header_float(header, 10),
        "temperature_c": _header_float(header, 36),
        "adc_rate": _unpack(header, 190, "<H") or None,
        "adc_gain": str(_unpack(header, 198, "<H")) if _unpack(header, 198, "<H") else None,
        "readout_time_ms": _header_float(header, 672),
        "geometric": ", ".join(name for bit, name in enumerate(_GEOMETRIC) if flags & (1 << bit)) or None,
        "comments": " | ".join(c for c in comments if c) or None,
    }
    settings = [("header/version", f"{version:g}"), ("header/datatype", dtype.name),
                ("header/xDimDet", str(det[0])), ("header/yDimDet", str(det[1])),
                ("header/NumFrames", str(declared)), ("header/NumROI", str(n_roi))]
    settings += [(f"header/comments[{i}]", c) for i, c in enumerate(comments) if c]
    settings += [(f"header/ROI[{i}]", "startx={} endx={} groupx={} starty={} endy={} groupy={}".format(*roi))
                 for i, roi in enumerate(rois[:max(n_roi, 1)])]
    settings += [(f"summary/{k}", str(v)) for k, v in summary.items() if v not in (None, "")]
    return SpeFile(
        version=version, dtype=dtype, n_frames=n_frames, regions=tuple(regions),
        sensor=det if all(det) else None, summary={k: v for k, v in summary.items() if v not in (None, "")},
        settings=settings, warnings=warnings,
    )


def _datetime_v2(date: str, time: str) -> Optional[str]:
    """ISO 8601 from the header's "02Jul2018" date and "094615" local time."""
    months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    match = re.fullmatch(r"(\d{1,2})([A-Za-z]{3})(\d{4})", date)
    if not match or match.group(2).lower() not in months:
        return date or None
    iso = f"{match.group(3)}-{months.index(match.group(2).lower()) + 1:02d}-{int(match.group(1)):02d}"
    return f"{iso}T{time[:2]}:{time[2:4]}:{time[4:6]}" if re.fullmatch(r"\d{6}", time) else iso


# ---- shared helpers -------------------------------------------------------------------------------


def _unpack(header: bytes, offset: int, fmt: str):
    return struct.unpack_from(fmt, header, offset)[0]


def _header_float(header: bytes, offset: int) -> Optional[float]:
    value = float(_unpack(header, offset, "<f"))
    return value if np.isfinite(value) and value != 0 else None


def _text(header: bytes, offset: int, length: int) -> str:
    return header[offset:offset + length].split(b"\0", 1)[0].decode("latin1").strip()


def _clamp_frames(declared: int, frame_size: int, frame_stride: int, available: int, warnings: List[str]) -> int:
    if frame_size <= 0:
        raise SpeError("frames have no pixels")
    present = 0 if available < frame_size else (available - frame_size) // frame_stride + 1
    if declared != present:
        if declared > present or declared <= 0:
            warnings.append(f"the header declares {declared} frames, but the file holds {present}")
        n = present if declared <= 0 else min(declared, present)
    else:
        n = declared
    if n <= 0:
        raise SpeError("the file holds no complete frame")
    return n


def _frames_view(raw: memoryview, offset: int, n_frames: int, stride: int, height: int, width: int,
                 dtype: np.dtype) -> np.ndarray:
    """(frames, height, width) read-only view of frames `stride` bytes apart, without copying.

    Frames whose offset or stride isn't a multiple of the pixel size (odd metadata sizes)
    are copied out instead.
    """
    size = height * width * dtype.itemsize
    end = offset + (n_frames - 1) * stride + size
    if offset % dtype.itemsize == 0 and stride % dtype.itemsize == 0:
        pixels = np.frombuffer(raw, dtype=dtype, count=(end - offset) // dtype.itemsize, offset=offset)
        return np.lib.stride_tricks.as_strided(pixels, shape=(n_frames, height, width),
                                               strides=(stride, width * dtype.itemsize, dtype.itemsize),
                                               writeable=False)
    data = np.frombuffer(raw, dtype=np.uint8, count=end - offset, offset=offset)
    frames = [data[i * stride:i * stride + size].view(dtype) for i in range(n_frames)]
    return np.stack(frames).reshape(n_frames, height, width)


# ---- writing (tests, synthetic camera images) -------------------------------------------------------


def write_spe(frames: np.ndarray, *, exposure_s: float = 0.1, sensor_origin: Tuple[int, int] = (0, 0),
              binning: Tuple[int, int] = (1, 1), sensor_size: Optional[Tuple[int, int]] = None,
              timestamps_s: Optional[Sequence[float]] = None, temperature_c: Optional[float] = None) -> bytes:
    """A LightField-style SPE 3.0 file of one region: `frames` is (frames, height, width).

    Each frame is followed by an exposure-start time stamp (1 MHz ticks) and a frame
    tracking number, as LightField writes them when those options are on.
    """
    frames = np.asarray(frames)
    if frames.ndim == 2:
        frames = frames[None]
    dtype = frames.dtype.newbyteorder("<")
    formats = {np.dtype(v): key for key, v in _XML_DTYPES.items()}
    if dtype not in formats:
        raise ValueError(f"cannot write {frames.dtype} pixels")
    kind, bits = formats[dtype]
    n, height, width = frames.shape
    size = height * width * dtype.itemsize
    stride = size + 16
    stamps = np.asarray(timestamps_s if timestamps_s is not None else np.arange(n) * exposure_s, dtype=float)
    body = bytearray()
    for i in range(n):
        body += np.ascontiguousarray(frames[i], dtype=dtype).tobytes()
        body += struct.pack("<qq", int(round(stamps[i] * 1e6)), i + 1)

    sw, sh = sensor_size or (sensor_origin[0] + width * binning[0], sensor_origin[1] + height * binning[1])
    pixel_format = f"Monochrome{kind}{bits}"
    temperature = (f"<Temperature><SetPoint>{temperature_c:g}</SetPoint><Reading>{temperature_c:g}</Reading>"
                   "</Temperature>") if temperature_c is not None else ""
    xml = (
        f'<?xml version="1.0" encoding="utf-8"?>\n<SpeFormat version="3.0" xmlns="{XML_NS}">'
        f'<DataFormat><DataBlock type="Frame" version="1" count="{n}" pixelFormat="{pixel_format}" '
        f'size="{size}" stride="{stride}"><DataBlock type="Region" count="1" pixelFormat="{pixel_format}" '
        f'size="{size}" stride="{size}" calibrations="1" width="{width}" height="{height}"/></DataBlock></DataFormat>'
        '<MetaFormat><MetaBlock type="TimeStamp" event="ExposureStarted" metaDataType="TimeStamp" version="1" '
        'resolution="1000000" bitDepth="64"/><MetaBlock type="FrameTrackingNumber" metaDataType="FrameTrackingNumber" '
        'version="1" bitDepth="64"/></MetaFormat>'
        f'<Calibrations><SensorInformation id="1" width="{sw}" height="{sh}"/>'
        f'<SensorMapping id="1" x="{sensor_origin[0]}" y="{sensor_origin[1]}" width="{width * binning[0]}" '
        f'height="{height * binning[1]}" xBinning="{binning[0]}" yBinning="{binning[1]}"/></Calibrations>'
        '<DataHistories><DataHistory><Origin software="masksim.spe" created="2026-01-01T00:00:00"><Experiment>'
        '<Devices><Cameras><Camera model="Synthetic" serialNumber="0">'
        f'<ShutterTiming><ExposureTime>{exposure_s * 1e3:g}</ExposureTime></ShutterTiming>'
        f'<Sensor>{temperature}</Sensor></Camera></Cameras></Devices></Experiment></Origin></DataHistory>'
        '</DataHistories></SpeFormat>'
    ).encode("utf-8")

    header = bytearray(HEADER_SIZE)
    struct.pack_into("<f", header, 10, exposure_s)
    struct.pack_into("<H", header, 42, width)
    struct.pack_into("<h", header, 108, _HEADER_CODES.get(np.dtype(dtype), 3))
    struct.pack_into("<H", header, 656, height)
    struct.pack_into("<Q", header, 678, HEADER_SIZE + len(body))
    struct.pack_into("<i", header, 1446, n)
    struct.pack_into("<f", header, 1992, 3.0)
    struct.pack_into("<i", header, 2996, WINVIEW_ID)
    struct.pack_into("<H", header, 4098, LAST_VALUE)
    return bytes(header) + bytes(body) + xml
