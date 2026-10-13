"""Place the generated pigment on the recovered wall without changing older marks."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / 'artifacts/line-1/wall.png'
NEW = ROOT / 'artifacts/line-1/wall-v16.png'
JPEG = ROOT / 'dist/line-1/35.jpg'
RECORD = ROOT / 'dist/line-1/35.json'
REVIEW = ROOT / 'line-1/wall-review-35.json'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def decode_png(data):
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('not a PNG')
    position, header, compressed = 8, None, bytearray()
    while position < len(data):
        size = int.from_bytes(data[position:position+4], 'big')
        tag = data[position+4:position+8]
        payload = data[position+8:position+8+size]
        check = int.from_bytes(data[position+8+size:position+12+size], 'big')
        if zlib.crc32(tag + payload) != check:
            raise ValueError('PNG CRC mismatch')
        if tag == b'IHDR':
            header = struct.unpack('>IIBBBBB', payload)
        elif tag == b'IDAT':
            compressed.extend(payload)
        elif tag == b'IEND':
            break
        position += size + 12
    if header is None:
        raise ValueError('missing PNG header')
    width, height, depth, color, compression, filtering, interlace = header
    if depth != 8 or color not in (2, 6) or compression or filtering or interlace:
        raise ValueError('expected noninterlaced RGB or RGBA PNG')
    channels = 3 if color == 2 else 4
    stride = width * channels
    raw = zlib.decompress(compressed)
    if len(raw) != (stride + 1) * height:
        raise ValueError('PNG data length mismatch')
    rows, previous = [], bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        mode = raw[start]
        row = bytearray(raw[start+1:start+1+stride])
        for i in range(stride):
            left = row[i-channels] if i >= channels else 0
            above = previous[i]
            upper_left = previous[i-channels] if i >= channels else 0
            if mode == 0:
                predicted = 0
            elif mode == 1:
                predicted = left
            elif mode == 2:
                predicted = above
            elif mode == 3:
                predicted = (left + above) // 2
            elif mode == 4:
                estimate = left + above - upper_left
                differences = (abs(estimate-left), abs(estimate-above),
                               abs(estimate-upper_left))
                predicted = (left, above, upper_left)[differences.index(min(differences))]
            else:
                raise ValueError('unknown PNG filter')
            row[i] = (row[i] + predicted) & 255
        rows.append(row)
        previous = row
    return width, height, channels, rows


def encode_rgb(rows, width, height):
    def chunk(tag, payload):
        return (len(payload).to_bytes(4, 'big') + tag + payload +
                zlib.crc32(tag + payload).to_bytes(4, 'big'))
    scanlines = b''.join(b'\x00' + bytes(row) for row in rows)
    return (b'\x89PNG\r\n\x1a\n' +
            chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(scanlines, 6)) + chunk(b'IEND', b''))


def main():
    old_png = OLD.read_bytes()
    previous = json.loads((ROOT / 'dist/line-1/34.json').read_text())
    assert digest(old_png) == previous['image'].rsplit('/', 1)[-1]
    generated = NEW.read_bytes()
    width, height, channels, old_rows = decode_png(old_png)
    gw, gh, gc, mark_rows = decode_png(generated)
    assert (width, height, channels) == (1254, 1254, 3)
    assert (gw, gh, gc) == (1536, 1024, 4)
    left, top, patch_width, patch_height = 60, 405, 118, 96
    source_left, source_top, source_width, source_height = 430, 245, 665, 545
    changed = 0
    for y in range(patch_height):
        sy = source_top + (y * source_height // patch_height)
        for x in range(patch_width):
            sx = source_left + (x * source_width // patch_width)
            p = sx * 4
            r, g, b, alpha = mark_rows[sy][p:p+4]
            if alpha < 165:
                continue
            # Retain the hand-rubbed pigment, excluding its generated brown glow.
            red = r > 65 and r > g * 1.3 and r > b * 1.55
            charcoal = max(r, g, b) < 115
            if not (red or charcoal):
                continue
            at = (left + x) * 3
            old = old_rows[top+y][at:at+3]
            pigment = ((149, 60, 30) if red else (40, 29, 21))
            strength = min(0.78, alpha / 255 * 0.72)
            new = bytes(round(old[i] * (1-strength) + pigment[i] * strength)
                        for i in range(3))
            if new != old:
                old_rows[top+y][at:at+3] = new
                changed += 1
    assert changed > 250, changed
    final_png = encode_rgb(old_rows, width, height)
    # Re-decode the written format before deriving the thumbnail.
    fw, fh, fc, final_rows = decode_png(final_png)
    assert (fw, fh, fc) == (1254, 1254, 3)
    spec = importlib.util.spec_from_file_location('thumbnail', ROOT / 'gathering/make_thumbnail.py')
    thumbnail = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(thumbnail)
    jpeg = thumbnail.jpeg(thumbnail.resize(width, height, final_rows))
    assert len(jpeg) < 100000
    NEW.write_bytes(final_png)
    OLD.write_bytes(final_png)
    JPEG.write_bytes(jpeg)
    meaning = ('Two ochre watchers face one charcoal stone, as a second provider '
               'checks a saved observation.')
    record = {'name': 'Two Watchers, One Stone',
              'image': 'https://api.imd.fun/artifacts/' + digest(final_png),
              'attributes': [{'trait_type': key, 'value': value} for key, value in (
                  ('Cave', 'Base'), ('Wall', 'Line 1'), ('Number', 35),
                  ('Left behind', 'snapshot-crosscheck'), ('Meaning', meaning),
                  ('One thing', 'portable live Ethereum state snapshots'))]}
    assert not RECORD.exists()
    RECORD.write_text(json.dumps(record, indent=2) + '\n')
    review = {
        'source_record': 34, 'record_number': 35, 'source_sha256': digest(old_png),
        'generated_sha256': digest(generated), 'wall_sha256': digest(final_png),
        'png_dimensions': [1254, 1254], 'png_format': '8-bit RGB PNG',
        'png_bytes': len(final_png), 'jpeg_dimensions': [512, 512],
        'jpeg_format': 'baseline JPEG', 'jpeg_bytes': len(jpeg),
        'addition_rectangle': [left, top, patch_width, patch_height],
        'changed_pixels': changed, 'changed_pixels_outside_rectangle': 0,
        'new_hands_or_stencils': 0,
        'unmet_visual_requirements': [
            'The inherited cave rock has a photographic appearance and was preserved.'],
    }
    REVIEW.write_text(json.dumps(review, indent=2) + '\n')
    print(json.dumps(review, indent=2))


if __name__ == '__main__':
    main()
