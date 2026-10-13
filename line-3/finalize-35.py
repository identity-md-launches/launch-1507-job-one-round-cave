"""Composite one generated pigment mark onto verified round-34 wall bytes.

The image tool's PNG enters as one base64 stdin stream; no cutout image is
stored. The old wall is hash checked, and pixels outside the small mark box
are retained exactly. This script never reads environment variables.
"""

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("image_helpers", ROOT / "line-3/finalize-31.py")
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
thumbnail = helpers.thumbnail


def pigment(red, green, blue):
    if max(red, green, blue) < 105:
        return (37, 29, 21), 190
    if red > green * 1.35 and red > blue * 1.45:
        return (140, 58, 32), 165
    if red > blue * 1.5 and green > blue * 1.3:
        return (165, 105, 47), 150
    if min(red, green, blue) > 165:
        return (203, 187, 155), 75
    return (103, 64, 39), 110


def main():
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        raise ValueError("supply exact base64 input byte count")
    count = int(sys.argv[1])
    if not 0 < count <= 12_000_000:
        raise ValueError("generated pigment input is too large")
    previous_path = ROOT / "artifacts/line-3/wall.png"
    previous = previous_path.read_bytes()
    inherited_hash = hashlib.sha256(previous).hexdigest()
    record_34 = json.loads((ROOT / "dist/line-3/34.json").read_text())
    if record_34["image"] != "https://api.imd.fun/artifacts/" + inherited_hash:
        raise ValueError("inherited wall does not match record 34")
    width, height, originals = thumbnail.png_rgb(previous)
    if (width, height) != (1254, 1254):
        raise ValueError("inherited wall has unexpected size")
    source = base64.b64decode(sys.stdin.buffer.read(count), validate=True)
    source_width, source_height, source_rows = helpers.png_rgba(source)

    # Clear rock between the ancestral scale and the upper-right pebble marks.
    box = (710, 160, 910, 280)
    x0, y0, x1, y1 = box
    target_width, target_height = x1 - x0, y1 - y0
    rows = [bytearray(row) for row in originals]
    changed = 0
    for dy in range(target_height):
        sy0 = dy * source_height // target_height
        sy1 = (dy + 1) * source_height // target_height
        for dx in range(target_width):
            sx0 = dx * source_width // target_width
            sx1 = (dx + 1) * source_width // target_width
            red = green = blue = alpha = 0
            samples = (sy1 - sy0) * (sx1 - sx0)
            for sy in range(sy0, sy1):
                source_row = source_rows[sy]
                for sx in range(sx0, sx1):
                    r, g, b, a = source_row[4 * sx:4 * sx + 4]
                    red += r * a
                    green += g * a
                    blue += b * a
                    alpha += a
            if alpha < samples * 25:
                continue
            color, strength = pigment(red // alpha, green // alpha, blue // alpha)
            opacity = min(strength, (alpha * strength + samples * 127) // (samples * 255))
            if opacity < 10:
                continue
            at = 3 * (x0 + dx)
            old = rows[y0 + dy][at:at + 3]
            new = bytes((old[channel] * (255 - opacity) + color[channel] * opacity + 127) // 255
                        for channel in range(3))
            if new != old:
                rows[y0 + dy][at:at + 3] = new
                changed += 1
    if changed < 2000:
        raise ValueError("new mark is missing or too faint")
    outside = sum(rows[y][3*x:3*x+3] != originals[y][3*x:3*x+3]
                  for y in range(height) for x in range(width)
                  if not (x0 <= x < x1 and y0 <= y < y1))
    if outside:
        raise ValueError("pixels changed outside the mark rectangle")

    png = helpers.encode_rgb(width, height, rows)
    if thumbnail.png_rgb(png)[2] != [bytes(row) for row in rows]:
        raise ValueError("PNG round trip differs")
    jpeg = thumbnail.jpeg(thumbnail.resize(width, height, rows))
    if len(jpeg) >= 100_000:
        raise ValueError("JPEG exceeds 100 KB")
    digest = hashlib.sha256(png).hexdigest()
    meaning = "Pepe watches rising embers approach an arch as a promise meets its fee limit."
    record = {"name": "Pepe's Ember Horizon",
              "image": "https://api.imd.fun/artifacts/" + digest,
              "attributes": [{"trait_type": key, "value": value} for key, value in [
                  ("Cave", "Base"), ("Wall", "Line 3"), ("Number", 35),
                  ("Left behind", "fee-horizon"), ("Meaning", meaning),
                  ("One thing", "Offline EIP-1559 transaction decoding")]]}
    version_path = ROOT / "artifacts/line-3/wall-v16.png"
    version_path.write_bytes(png)
    previous_path.write_bytes(png)
    (ROOT / "dist/line-3/35.jpg").write_bytes(jpeg)
    (ROOT / "dist/line-3/35.json").write_text(json.dumps(record, indent=2) + "\n")
    review = {
        "wall": {"paths": ["artifacts/line-3/wall-v16.png", "artifacts/line-3/wall.png"],
                 "width": width, "height": height, "format": "PNG", "mode": "RGB",
                 "bytes": len(png), "sha256": digest},
        "thumbnail": {"path": "dist/line-3/35.jpg", "width": 512, "height": 512,
                      "format": "JPEG", "bytes": len(jpeg)},
        "preservation": {"inheritedSha256": inherited_hash,
                         "editRectangleXYXY": list(box), "changedPixels": changed,
                         "changedPixelsOutsideRectangle": outside},
        "cutout": {"width": source_width, "height": source_height,
                   "format": "PNG", "mode": "RGBA"},
        "visualReview": {"reviewed": False, "method": "pending final PNG and JPEG inspection"},
        "unmetVisualRequirements": ["Visual inspection pending"]}
    (ROOT / "line-3/round-35-review.json").write_text(json.dumps(review, indent=2) + "\n")
    print(json.dumps(review, indent=2))


if __name__ == "__main__":
    main()
