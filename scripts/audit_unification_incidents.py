"""Read certification evidence/throughput without running any workers or writes."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import re
import statistics
import unicodedata

CASES = ('carames', 'diego malizia', 'cipollone', 'blanco', 'bottega', 'cavacini',
         'ciam', 'espina', 'berardi', 'constant', 'ventasprop', 'andrade',
         'benitez ullo', 'cip', 'blangiforti', 'arte', 'emir elhelou',
         'analia requena', 'alejandro foster')


def fold(text):
    return re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in unicodedata.normalize('NFKD', text.lower())
                                           if not unicodedata.combining(c))).strip()


def audit(directory):
    attempts = []
    malformed = 0
    with (directory / 'AGENCY_CERTIFICATION_RESULTS.jsonl').open(encoding='utf-8') as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                attempts.append(json.loads(line))
            except ValueError:
                malformed += 1
    latest = {}
    for row in attempts:
        key = row.get('canonical_agency_id')
        if key:
            latest[key] = row
    controls = {}
    for case in CASES:
        pattern = r'\b' + re.escape(case).replace(r'\ ', r'\s*') + r'\b'
        # Compound surnames sometimes appear joined in a canonical slug.
        compact = case.replace(' ', '')
        matches = [row for key, row in latest.items()
                   if re.search(pattern, fold(key + ' ' + str(row.get('agency_name') or '')))
                   or (len(compact) > 6 and compact in fold(key).replace(' ', ''))]
        controls[case] = [dict(canonical_id=r.get('canonical_agency_id'), status=r.get('status'),
                               reasons=r.get('reasons'), official_url=r.get('official_url'),
                               connector=r.get('connector'), strategy=r.get('connector_strategy'),
                               checked_at=r.get('checked_at'), enumeration=r.get('enumeration_audit'),
                               field_states={k: v.get('state') for k, v in (r.get('field_coverage') or {}).items()})
                          for r in matches]
    per_day = Counter()
    durations = []
    dates = []
    for row in attempts:
        stamp = row.get('checked_at') or ''
        if stamp:
            per_day[stamp[:10]] += 1
            try:
                dates.append(datetime.fromisoformat(stamp).replace(tzinfo=None))
            except ValueError:
                pass
        duration = sum((row.get(run) or {}).get('segundos') or 0 for run in ('run1', 'run2'))
        if duration > 0:
            durations.append(duration)
    elapsed_days = (max(dates) - min(dates)).total_seconds() / 86400 if dates else 0
    return dict(schema='eretz_operational_audit_v1', attempts=len(attempts), agencies=len(latest),
                latest_statuses=dict(Counter(r.get('status') for r in latest.values())),
                attempts_per_reported_day=dict(sorted(per_day.items())), malformed_lines=malformed,
                observed_elapsed_days=round(elapsed_days, 2),
                unique_agencies_per_elapsed_day=round(len(latest) / elapsed_days, 2) if elapsed_days else None,
                median_two_run_seconds=statistics.median(durations) if durations else None,
                controls=controls, database_writes=0,
                limitation='Recorded campaign history; elapsed throughput includes stoppages/retries. Not a national coverage ETA.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('certification', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.certification)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'controls'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
