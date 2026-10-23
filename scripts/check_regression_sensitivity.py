"""Prove selected tests reject deliberate regressions in a disposable source copy.

No mutation is applied to the checkout. No hardware, network, or user store is
used. A mutant counts as detected only for assertion failures, never for a
collection/import error. This is a targeted sensitivity check, not a global
mutation-coverage score.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
MUTATIONS=[
    ('search_no_retry','jarvis/knowledge/service.py',
     'return list(dict.fromkeys(attempts))[:3]', 'return list(dict.fromkeys(attempts))[:1]',
     'tests/test_search_resilience.py::test_empty_failed_or_unusable_first_search_recovers'),
    ('document_consent_bypassed','jarvis/capabilities/document.py',
     'permission=REMOTE_DOCUMENT_PERMISSION.get()', 'return None\n        permission=REMOTE_DOCUMENT_PERMISSION.get()',
     'tests/test_protection_contracts.py::test_document_text_never_leaves_without_effective_consent'),
    ('quiet_audio_audible','jarvis/desktop/live_audio.py',
     'if self.quiet:pcm = bytes(len(data))','if False:pcm = bytes(len(data))',
     'tests/test_voice_resilience_contracts.py::test_playback_respects_quiet_and_echo_contract'),
    ('expired_confirmation_accepted','jarvis/live/confirmation.py',
     'if now - item.created_at > self._ttl_seconds','if False',
     'tests/test_generated_invariants.py::TestConfirmationSequences'),
    ('read_only_guard_bypassed','jarvis/live/registry.py',
     'if getattr(self, "read_only_mode", False):','if False:',
     'tests/test_read_only_mode.py::ReadOnlyModeTests::test_blocked_tool_refuses_and_runs_nothing_in_safe_mode'),
]


def run_tests(root, targets, report):
    env=dict(os.environ,PYTHONPATH=str(root/'src'),PYTHONDONTWRITEBYTECODE='1',QT_QPA_PLATFORM='offscreen')
    proc=subprocess.run([sys.executable,'-m','pytest','-q','--tb=short','--override-ini=addopts=',f'--junitxml={report}',*targets],
                        cwd=root,env=env,capture_output=True,text=True,timeout=90)
    if not report.exists():return {'returncode':proc.returncode,'failures':0,'errors':1}
    suites=ET.parse(report).getroot().iter('testsuite')
    values=list(suites)
    return {'returncode':proc.returncode,'failures':sum(int(s.get('failures',0)) for s in values),'errors':sum(int(s.get('errors',0)) for s in values)}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--json',type=Path);args=parser.parse_args()
    results=[]
    with tempfile.TemporaryDirectory(prefix='jarvis-regression-sensitivity-') as directory:
        root=Path(directory)
        ignore=shutil.ignore_patterns('__pycache__','*.pyc')
        shutil.copytree(ROOT/'src',root/'src',ignore=ignore)
        shutil.copytree(ROOT/'tests',root/'tests',ignore=ignore)
        baseline=run_tests(root,[item[4] for item in MUTATIONS],root/'baseline.xml')
        if baseline['returncode']!=0:
            print(json.dumps({'baseline_passed':False,**baseline}));return 1
        for name,path,before,after,target in MUTATIONS:
            file=root/'src'/path;original=file.read_text()
            if original.count(before)!=1:raise RuntimeError(f'Mutation anchor changed: {name}')
            try:
                file.write_text(original.replace(before,after))
                outcome=run_tests(root,[target],root/(name+'.xml'))
                detected=outcome['returncode']==1 and outcome['failures']>0 and outcome['errors']==0
                results.append({'name':name,'detected':detected,**outcome})
                print(f'{name}: {"DETECTED" if detected else "NOT DETECTED"}',flush=True)
            finally:file.write_text(original)
    report={'baseline_passed':True,'mutations':results}
    if args.json:args.json.write_text(json.dumps(report,indent=2)+'\n')
    return 0 if all(r['detected'] for r in results) else 1

if __name__=='__main__':raise SystemExit(main())
