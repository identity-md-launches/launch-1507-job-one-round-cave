#!/usr/bin/env python3
"""Check Gathering 15's output contract without network or image libraries."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'gathering/checks/round-15/deliverable.json'
PLACEHOLDER = {'name': 'Not painted yet',
               'image': 'https://api.imd.fun/artifacts/9cbb7bb2a41efa92e010921f287819c9ffb02c4375fa9496c8468701d8e00cc5',
               'attributes': [{'trait_type': 'Cave', 'value': 'Base'}]}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Gallery(HTMLParser):
    def __init__(self):
        super().__init__()
        self.section = None
        self.cards = {}
        self.scripts = 0

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'section':
            self.section = values['id']
            self.cards[self.section] = []
        elif tag == 'article':
            self.cards[self.section].append(int(values['data-number']))
        elif tag == 'script':
            self.scripts += 1


def main():
    wall = ROOT / 'artifacts/gathering/wall-v16.png'
    same = ROOT / 'artifacts/gathering/wall.png'
    preview = ROOT / 'dist/gathering/15.jpg'
    record = json.loads((ROOT / 'dist/gathering/15.json').read_text())
    assert set(record) == {'name', 'image', 'attributes'}
    assert [row['trait_type'] for row in record['attributes']] == [
        'Cave', 'Wall', 'Number', 'Left behind', 'Meaning', 'One thing']
    assert all(set(row) == {'trait_type', 'value'} for row in record['attributes'])
    assert [record['attributes'][i]['value'] for i in (0, 1, 2, 5)] == [
        'Base', 'Gathering', 15, 'Gathering']
    assert type(record['attributes'][2]['value']) is int
    assert record['image'] == 'https://api.imd.fun/artifacts/' + sha(wall)
    assert wall.read_bytes() == same.read_bytes()
    assert {p.name for p in (ROOT / 'artifacts/gathering').iterdir()} == {
        'wall-v16.png', 'wall.png'}
    data = wall.read_bytes()
    assert data[:8] == b'\x89PNG\r\n\x1a\n' and data[12:16] == b'IHDR'
    width, height, depth, color, compression, filtering, interlace = struct.unpack_from(
        '>IIBBBBB', data, 16)
    assert (width, height, depth, color, compression, filtering, interlace) == (
        1254, 1254, 8, 2, 0, 0, 0)
    from check_deliverable import png_dimensions, jpeg_dimensions
    assert png_dimensions(data) == (1254, 1254)
    assert jpeg_dimensions(preview.read_bytes()) == (512, 512)
    info = {'width': 512, 'height': 512}
    assert preview.stat().st_size < 100000
    review = json.loads((ROOT / 'gathering/checks/round-15/image-preservation.json').read_text())
    assert review['changed_pixels'] > 0 and review['changed_pixels_outside_rectangle'] == 0
    assert review['unmet_visual_requirements'] == []

    goals = [{'line': n, 'goal': (ROOT / f'line-{n}/GOAL.md').read_text().strip()}
             for n in range(1, 5)]
    assert json.loads((ROOT / 'dist/goals.json').read_text()) == goals
    gallery = Gallery()
    page = (ROOT / 'dist/index.html').read_text()
    gallery.feed(page)
    assert gallery.scripts == 0 and len(page.encode()) < 100000
    count = 0
    for folder in ['line-1', 'line-2', 'line-3', 'line-4', 'gathering']:
        records = sorted((ROOT / 'dist' / folder).glob('[0-9][0-9].json'), reverse=True)
        painted, pending = [], []
        for path in records:
            item = json.loads(path.read_text())
            number = int(path.stem)
            if item['name'] == 'Not painted yet':
                assert item == PLACEHOLDER and not path.with_suffix('.jpg').exists()
                pending.append(number)
            else:
                assert path.with_suffix('.jpg').exists()
                painted.append(number)
        assert all((ROOT / 'dist' / folder / f'{n:02d}.json').exists()
                   for n in range(2, 22))
        assert gallery.cards[folder] == painted + pending
        count += len(records)
    assert count == 161

    baseline = json.loads((ROOT / 'gathering/round-15-line-hashes.json').read_text())
    actual = {str(p.relative_to(ROOT)): sha(p) for n in range(1, 5)
              for p in sorted((ROOT / f'line-{n}').rglob('*')) if p.is_file()}
    assert actual == baseline, 'line source bytes or file set changed'
    provenance = json.loads((ROOT / 'shared/horizon-context/PROVENANCE.json').read_text())
    for item in provenance:
        assert sha(ROOT / item['source']) == item['sha256']
        assert sha(ROOT / 'shared/horizon-context' / item['copy']) == item['sha256']
    changed = subprocess.check_output(['git', 'status', '--porcelain', '-z', '--untracked-files=all'], cwd=ROOT)
    paths = [entry[3:].decode() for entry in changed.split(b'\0') if entry]
    assert all(path.startswith(('gathering/', 'shared/', 'artifacts/gathering/', 'dist/')) for path in paths)
    assert not subprocess.check_output(['git', 'status', '--porcelain', '--', 'line-1', 'line-2', 'line-3', 'line-4'], cwd=ROOT)
    assert not subprocess.check_output(['git', 'ls-files', '--', 'artifacts/gathering'], cwd=ROOT)
    assert all(not p.is_symlink() for folder in ('gathering', 'shared', 'dist')
               for p in (ROOT / folder).rglob('*'))
    assert all(p.stat().st_size < 100000 for folder in ('gathering', 'shared', 'dist')
               for p in (ROOT / folder).rglob('*') if p.is_file())
    assert (ROOT / 'gathering/COINS.md').read_text().startswith('none\n')
    report = (ROOT / 'gathering/REPORT.md').read_text()
    assert all(f'## Line {n}' in report for n in range(1, 5))
    assert all(item['exit'] == 0 for item in json.loads((ROOT / 'gathering/checks/round-15/tool-checks.json').read_text()))
    assert not (ROOT / 'gathering/coin-order.json').exists()
    assert not (ROOT / 'gathering/deploy-order.json').exists()
    assert json.loads((ROOT / 'gathering/checks/round-15/horizon-tests.json').read_text())['exit'] == 0
    result = {'passed': True, 'record_number': 15, 'wall_dimensions': [width, height],
              'wall_format': '8-bit RGB PNG', 'wall_sha256': sha(wall),
              'preview_dimensions': [info['width'], info['height']],
              'preview_format': 'JPEG', 'preview_bytes': preview.stat().st_size,
              'changed_pixels_outside_rectangle': 0, 'unmet_visual_requirements': [],
              'gallery_records': count, 'gallery_bytes': len(page.encode()),
              'source_paths_in_scope': True, 'line_folders_unchanged': True,
              'shared_source_hashes_match': True}
    OUT.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
