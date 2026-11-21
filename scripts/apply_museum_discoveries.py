"""Import reviewed museum website discoveries and source-backed exhibition notes."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from apply_expositions import ROOT, domain, validate_record


def write_json(path, data):
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('reviewed', type=Path, help='Array of results reviewed by internal Luna')
    args = parser.parse_args()
    museum_path = ROOT/'data/museums.json'
    note_path = ROOT/'data/exposition-notes.json'
    museums = json.loads(museum_path.read_text(encoding='utf8'))
    by_id = {m['id']: m for m in museums}
    notes = json.loads(note_path.read_text(encoding='utf8'))
    updated = datetime.now(timezone.utc).isoformat()
    domains = set()
    for row in json.loads(args.reviewed.read_text(encoding='utf-8-sig')):
        museum = by_id[row['id']]
        website = row.get('official_url')
        if website:
            url = urlsplit(website)
            if url.scheme not in ('http','https') or not url.hostname or url.username:
                raise ValueError(f'Invalid official URL for {row["id"]}')
            if website not in museum['sites']:
                museum['sites'].append(website)
            domains.add(domain(website))
        facts = row.get('facts', [])
        if not facts:
            continue
        evidence = row['evidence']
        source = facts[0]['source']
        # A municipality may document an exhibit without hosting the museum site.
        _, accepted = validate_record({'museum_ids':[row['id']], 'scope':'venue', 'facts':facts},
                                      {'key':domain(source)}, evidence,
                                      {row['id']: {'sites':[source]}})
        notes['museums'][row['id']] = {
            'facts':accepted, 'checked_at':updated, 'domain':domain(facts[0]['source']),
            'processor':'internal-luna', 'evidence_hash':'', 'status':'verified',
        }
    notes['updated_at'] = updated
    write_json(museum_path, museums)
    write_json(note_path, notes)
    print(','.join(sorted(domains)))


if __name__ == '__main__':
    main()
