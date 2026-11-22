"""Draws the app icon (a radar sweep) as PNG/ICO with the standard library only."""
from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

BG = (29, 28, 26)
ACCENT = (224, 132, 84)
RING = (120, 74, 50)


def _png(size: int) -> bytes:
    ss = 3  # supersampling for smooth edges
    c = (size - 1) / 2
    radius = size * 0.5
    corner = size * 0.22
    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            acc = [0.0, 0.0, 0.0, 0.0]
            for sy in range(ss):
                for sx in range(ss):
                    px = x + (sx + 0.5) / ss - 0.5
                    py = y + (sy + 0.5) / ss - 0.5
                    # rounded-square mask
                    qx = max(abs(px - c) - (radius - corner), 0)
                    qy = max(abs(py - c) - (radius - corner), 0)
                    if math.hypot(qx, qy) > corner:
                        continue
                    dx, dy = px - c, py - c
                    d = math.hypot(dx, dy) / (size * 0.40)
                    col = BG
                    ang = (math.degrees(math.atan2(dy, dx)) + 360) % 360
                    sweep = (ang - 230) % 360  # wedge trailing behind the beam
                    if d <= 1 and sweep <= 70:
                        t = 1 - sweep / 70
                        col = tuple(int(BG[i] + (ACCENT[i] - BG[i]) * t * 0.55) for i in range(3))
                    for r in (0.36, 0.68, 1.0):
                        if abs(d - r) < 0.035:
                            col = RING
                    if d <= 1 and abs(sweep) < 2.2:
                        col = ACCENT
                    if math.hypot(px - (c + size * 0.17), py - (c - size * 0.20)) < size * 0.055:
                        col = ACCENT
                    if math.hypot(dx, dy) < size * 0.045:
                        col = ACCENT
                    acc[0] += col[0]; acc[1] += col[1]; acc[2] += col[2]; acc[3] += 255
            if acc[3]:
                covered = acc[3] / 255  # number of samples inside the shape
                rows += bytes((int(acc[0] / covered), int(acc[1] / covered), int(acc[2] / covered),
                               int(acc[3] / (ss * ss))))
            else:
                rows += b"\0\0\0\0"

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + chunk(b"IEND", b""))


def ensure_icons(folder: Path) -> dict[str, Path]:
    """Create icon.png (256px) and icon.ico (PNG-compressed, Vista+) once."""
    folder.mkdir(parents=True, exist_ok=True)
    png_path, ico_path = folder / "icon.png", folder / "icon.ico"
    if not png_path.exists() or not ico_path.exists():
        big = _png(256)
        png_path.write_bytes(big)
        images = [(s, _png(s)) for s in (16, 32, 48)] + [(256, big)]
        header = struct.pack("<HHH", 0, 1, len(images))
        offset = 6 + 16 * len(images)
        entries, blobs = b"", b""
        for s, data in images:
            entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), offset + len(blobs))
            blobs += data
        ico_path.write_bytes(header + entries + blobs)
    return {"png": png_path, "ico": ico_path}
