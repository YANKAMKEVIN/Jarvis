"""Build a family-level regression ledger from actual pytest JUnit results.

This reports executed assertions, not user-journey or hardware qualification.
Unknown test files stay visible in 'transverse'; no test result is discarded.
"""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

FAMILIES = {
    'web': ('knowledge', 'search', 'keyless', 'webread', 'live_answer'),
    'documents': ('document', 'pdf'),
    'compute': ('compute',),
    'files': ('files', 'filesystem', 'spotlight'),
    'personal_data': ('notes', 'qa_note', 'memory', 'context', 'productivity', 'checklist'),
    'desktop_control': ('app_capability', 'window', 'keyboard', 'mouse', 'accessibility', 'click_element', 'interaction'),
    'browser': ('browser',),
    'system_media': ('system', 'audio_capability', 'media_capability'),
    'clipboard_text': ('clipboard', 'text_workshop'),
    'calendar': ('calendar', 'briefing'),
    'messaging': ('mail', 'imap', 'messaging', 'whatsapp', 'confirmation'),
    'scheduling': ('schedule', 'reminder', 'qa_delivery'),
    'missions': ('planner', 'mission', 'macro', 'request_routing', 'shortcuts', 'qa_resilience'),
    'claude': ('claude',),
    'metrics': ('insights', 'usage'),
    'vision': ('vision', 'screenshot'),
    'privacy': ('privacy', 'clear_personal', 'read_only', 'protection', 'archive'),
    'voice_interface': ('desktop', 'voice', 'wakeword'),
    'camera_wip': ('camera',),
}


def report(xml):
    root = ET.parse(xml).getroot()
    families = {}
    for case in root.iter('testcase'):
        name = case.get('classname', '')
        file = next((part[5:] for part in name.split('.') if part.startswith('test_')), name)
        family = next((key for key, patterns in FAMILIES.items() if any(p in file for p in patterns)), 'transverse')
        row = families.setdefault(family, {'passed': 0, 'failed': 0, 'skipped': 0, 'seconds': 0., 'cases': []})
        status = 'failed' if case.find('failure') is not None or case.find('error') is not None else 'skipped' if case.find('skipped') is not None else 'passed'
        row[status] += 1
        row['seconds'] += float(case.get('time', 0))
        row['cases'].append({'id': name + '::' + case.get('name',''), 'status': status})
    return {'evidence': 'Executed offline pytest assertions; native and service backends may be mocked. Times include setup, not user latency.',
            'global_product_qualified': False,
            'real_world_pending': ['microphone and speakers', 'two-hour endurance', 'private test accounts', 'native target/focus races', 'screen and device changes'],
            'families': families}


START, END = '<!-- qa-table:start -->', '<!-- qa-table:end -->'


def markdown_table(result, mutations=None, date=''):
    """Per-family table for docs/testing-quality.md, generated from real results."""
    rows = sorted(result['families'].items(), key=lambda item: -item[1]['passed'])
    lines = ['| Famille | Réussis | Échecs | Ignorés |', '|---|---:|---:|---:|']
    lines += [f"| {name} | {row['passed']} | {row['failed']} | {row['skipped']} |" for name, row in rows]
    total = {key: sum(row[key] for _, row in rows) for key in ('passed', 'failed', 'skipped')}
    lines.append(f"| **Total** | **{total['passed']}** | **{total['failed']}** | **{total['skipped']}** |")
    if mutations is not None:
        detected = sum(1 for m in mutations.get('mutations', []) if m.get('detected'))
        lines += ['', f"Mutations ciblées détectées : **{detected} / {len(mutations.get('mutations', []))}**."]
    if date:
        lines += ['', f'Tableau généré le {date} par `scripts/report_qa.py --update-doc`.']
    return '\n'.join(lines)


def update_doc(path, table):
    text = path.read_text(encoding='utf-8')
    if START not in text or END not in text:
        raise SystemExit(f'Marqueurs {START} / {END} absents de {path}')
    before, rest = text.split(START, 1)
    _, after = rest.split(END, 1)
    path.write_text(before + START + '\n' + table + '\n' + END + after, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--junit', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mutations', type=Path, help='JSON de check_regression_sensitivity.py, pour le tableau')
    parser.add_argument('--update-doc', type=Path, help='réécrit le tableau entre les marqueurs qa-table de ce fichier')
    args = parser.parse_args()
    result = report(args.junit)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    if args.update_doc:
        import datetime
        mutations = json.loads(args.mutations.read_text()) if args.mutations else None
        update_doc(args.update_doc, markdown_table(result, mutations, datetime.date.today().isoformat()))
    for name, row in result['families'].items():
        print(f"{name}: {row['passed']} passed, {row['failed']} failed, {row['skipped']} skipped")
    return int(any(row['failed'] for row in result['families'].values()) or not result['families'])


if __name__ == '__main__':
    raise SystemExit(main())
