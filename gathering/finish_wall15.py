#!/usr/bin/env python3
"""Add generated pigment to vacant rock, preserving every ancestor elsewhere."""
import hashlib
import json
from pathlib import Path

from finish_wall8 import encode_png
from make_thumbnail import jpeg, png_rgb, resize

SOURCE_SHA = '17e6c21c4836254c1f4576d4cd97557534537b6120b4d98fab45451d5ae3fa87'
RECT = (725, 180, 145, 100)


def main():
    source = Path('artifacts/gathering/wall.png').read_bytes()
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA:
        raise ValueError('source differs from ancestral gathering record 14')
    width, height, old = png_rgb(source)
    generated_path = Path('artifacts/gathering/wall-v16.png')
    motif_raw = generated_path.read_bytes()
    mw, mh, motif = png_rgb(motif_raw)
    if (width, height) != (1254, 1254):
        raise ValueError('ancestral wall dimensions changed')
    points = [(x, y) for y, row in enumerate(motif) for x in range(mw)
              if min(row[3*x:3*x+3]) < 180]
    if not points:
        raise ValueError('no generated pigment')
    x0 = max(0, min(x for x, _ in points)-7)
    x1 = min(mw, max(x for x, _ in points)+8)
    y0 = max(0, min(y for _, y in points)-7)
    y1 = min(mh, max(y for _, y in points)+8)
    left, top, rw, rh = RECT
    result = [bytearray(row) for row in old]
    for dy in range(rh):
        sy0 = y0 + dy*(y1-y0)//rh
        sy1 = max(sy0+1, y0+(dy+1)*(y1-y0)//rh)
        for dx in range(rw):
            sx0 = x0 + dx*(x1-x0)//rw
            sx1 = max(sx0+1, x0+(dx+1)*(x1-x0)//rw)
            amount = red = green = blue = 0
            for sy in range(sy0, sy1):
                for sx in range(sx0, sx1):
                    pixel = motif[sy][3*sx:3*sx+3]
                    r, g, b = pixel
                    # White source paper contributes nothing; preserve dry texture.
                    a = max(0.0, min(0.82, (240-min(pixel))/205 * 0.82))
                    if r > g*1.4 and r > 65:
                        pigment = (143, 62, 29)  # Red ochre.
                    elif r > b*1.7 and g > b*1.3 and r > 100:
                        pigment = (185, 126, 49)  # Yellow ochre.
                    elif min(pixel) > 160 and max(pixel)-min(pixel) < 45:
                        pigment = (204, 181, 137)  # Worn chalk.
                    else:
                        pigment = (24, 19, 15)  # Charcoal.
                    amount += a
                    red += a*pigment[0]
                    green += a*pigment[1]
                    blue += a*pigment[2]
            if amount == 0:
                continue
            count = (sy1-sy0)*(sx1-sx0)
            alpha = amount/count
            pigment = (red/amount, green/amount, blue/amount)
            x, y = left+dx, top+dy
            stone = old[y][3*x:3*x+3]
            result[y][3*x:3*x+3] = bytes(round(a*(1-alpha)+b*alpha)
                                        for a, b in zip(stone, pigment))
    changed = outside = 0
    for y in range(height):
        for x in range(width):
            if old[y][3*x:3*x+3] != result[y][3*x:3*x+3]:
                changed += 1
                outside += not (left <= x < left+rw and top <= y < top+rh)
    if changed < 1000 or outside:
        raise ValueError('unexpected pigment extent or ancestor pixel changes')
    wall = encode_png(width, height, result)
    thumbnail = jpeg(resize(width, height, result))
    if len(thumbnail) >= 100000:
        raise ValueError('thumbnail exceeds 100 KB')
    generated_path.write_bytes(wall)
    Path('artifacts/gathering/wall.png').write_bytes(wall)
    Path('dist/gathering/15.jpg').write_bytes(thumbnail)
    review = {'source_record': 14, 'record_number': 15,
              'source_sha256': SOURCE_SHA,
              'wall_sha256': hashlib.sha256(wall).hexdigest(),
              'png_dimensions': [width, height], 'png_format': '8-bit RGB PNG',
              'png_bytes': len(wall), 'jpeg_dimensions': [512, 512],
              'jpeg_format': 'baseline JPEG', 'jpeg_bytes': len(thumbnail),
              'generated_motif_dimensions': [mw, mh],
              'generated_motif_sha256': hashlib.sha256(motif_raw).hexdigest(),
              'motif_crop': [x0, y0, x1, y1], 'addition_rectangle': list(RECT),
              'changed_pixels': changed, 'changed_pixels_outside_rectangle': outside,
              'method': 'Installed image tool motif; white paper removed in memory, earth pigment area-averaged into vacant rock.',
              'visual_review': 'pending final PNG and JPEG inspection'}
    Path('gathering/checks/round-15/image-preservation.json').write_text(
        json.dumps(review, indent=2)+'\n')
    print(json.dumps(review, indent=2))


if __name__ == '__main__':
    main()
