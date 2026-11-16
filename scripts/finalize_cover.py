#!/usr/bin/env python3
"""Copy approved artwork unchanged, verify hashes, and package deliverables."""

import argparse
import hashlib
import json
import math
import re
import shutil
import sys
import zipfile
from pathlib import Path


def sha256(path):
    result = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='New or empty delivery directory')
    parser.add_argument('--cover', action='append', required=True, metavar='LABEL=IMAGE',
                        help='Repeat for each platform; the same approved file may be reused')
    args = parser.parse_args()
    try:
        from PIL import Image
    except ImportError:
        parser.error('Pillow is required to verify image files; use an available Python runtime with Pillow.')

    prepared = []
    labels = set()
    for value in args.cover:
        label, separator, filename = value.partition('=')
        if not separator or not filename or not re.fullmatch(r'[a-z][a-z0-9_-]{0,40}', label):
            parser.error('Use LABEL=IMAGE with a lowercase ASCII label, e.g. douyin=approved.png')
        if label in labels:
            parser.error(f'Duplicate label: {label}')
        labels.add(label)
        source = Path(filename).expanduser().resolve()
        if not source.is_file():
            parser.error(f'Image not found: {source}')
        if source.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp'}:
            parser.error(f'Unsupported image extension: {source.suffix}')
        try:
            with Image.open(source) as picture:
                width, height = picture.size
                image_format = picture.format
                picture.verify()
        except (OSError, ValueError) as error:
            parser.error(f'Invalid image {source}: {error}')
        prepared.append({'label': label, 'source': source, 'width': width,
                         'height': height, 'format': image_format, 'sha256': sha256(source)})

    output = args.out.expanduser().resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error(f'Output must be a new or empty directory: {output}')
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for item in prepared:
        destination = output / f"{item['label']}-cover{item['source'].suffix.lower()}"
        shutil.copy2(item['source'], destination)
        result_hash = sha256(destination)
        if result_hash != item['sha256']:
            raise RuntimeError(f'Copy verification failed: {destination}')
        divisor = math.gcd(item['width'], item['height'])
        records.append({
            'label': item['label'], 'file': destination.name,
            'approved_source': str(item['source']), 'width': item['width'], 'height': item['height'],
            'aspect_ratio': f"{item['width'] // divisor}:{item['height'] // divisor}",
            'format': item['format'], 'bytes': destination.stat().st_size,
            'sha256': result_hash, 'identical_to_approved': True,
        })
    manifest = {
        'operation': 'unchanged copies of approved artwork; no image editing or platform validation',
        'same_artwork_for_all_labels': len({item['sha256'] for item in records}) == 1,
        'deliverables': records,
    }
    manifest_path = output / 'delivery-manifest.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    archive_path = output / 'covers-final.zip'
    with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for item in records:
            archive.write(output / item['file'], arcname=item['file'])
        archive.write(manifest_path, arcname=manifest_path.name)
    print(json.dumps({'output': str(output), 'manifest': str(manifest_path),
                      'archive': str(archive_path), 'same_artwork': manifest['same_artwork_for_all_labels'],
                      'files': [item['file'] for item in records]}, ensure_ascii=True))


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError) as error:
        print(f'Error: {error}', file=sys.stderr)
        sys.exit(1)
