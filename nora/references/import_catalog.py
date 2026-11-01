#!/usr/bin/env python3
"""Copy an explicit legacy reference inventory into a portable reference library."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil


def migrate(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    data = json.loads(source.read_text())
    if destination.exists():
        raise ValueError('Destination must not exist; create a new versioned library')
    prepared = []
    identifiers = set()
    for record in data['records']:
        ident = record['id']
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', ident) or ident in identifiers:
            raise ValueError('Invalid or duplicate reference ID')
        identifiers.add(ident)
        path = Path(record['path']).resolve(strict=True)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != record['sha256']:
            raise ValueError('Source reference changed; review inventory before importing')
        if path.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
            raise ValueError('Unsupported original reference format')
        metadata = {k: record[k] for k in ('id','category','title','status','tags','size','collection','parent_review') if k in record}
        metadata.update(source_kind='individual', path='originals/'+ident+path.suffix.lower(), sha256=digest)
        if record.get('collection') == 'head360' and re.fullmatch(r'H\d{3}', ident):
            metadata['angle'] = int(ident[1:])
        prepared.append((path, metadata))
    destination.mkdir(parents=True)
    try:
        (destination/'originals').mkdir()
        for path, metadata in prepared:
            shutil.copyfile(path, destination/metadata['path'])
        payload = {'version':1,'character':data.get('character','References'),
                   'policy':'Organize and upload reference photographs; download originals and export sheets; no inference or automatic training promotion.',
                   'records':[metadata for _,metadata in prepared], 'missing':data.get('missing',{})}
        (destination/'manifest.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
        # Private provenance is preserved separately, not exposed by the catalog API.
        (destination/'source-inventory.json').write_bytes(source.read_bytes())
    except BaseException:
        shutil.rmtree(destination)
        raise
    return {'records':len(prepared),'bytes':sum(path.stat().st_size for path,_ in prepared)}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('destination',type=Path)
    args=p.parse_args();print(json.dumps(migrate(args.source,args.destination)))

if __name__=='__main__':main()
