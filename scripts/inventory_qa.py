"""Inventory committed tool declarations and static test references, without running tools.

A reference in a test is not proof of a user journey. All real-world qualification
statuses start as pending. Uncommitted work is deliberately excluded.
"""
import argparse
import ast
from collections import Counter
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
CAPABILITIES={'audio','apps','media','system','windows','files','clipboard','keyboard','mouse','ui_accessibility','interaction','browser','screenshot','vision','messaging','memory','knowledge','schedule_store','reminder_store','calendar','mail','usage','system_metrics','insights','claude_sessions','compute','notes','diagnostics','shortcuts','macro_store','context_store','webread','document','pending_actions'}

def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True)

def inventory():
    paths=git('ls-tree','-r','--name-only','HEAD').splitlines()
    references={}
    for path in paths:
        if not path.startswith('tests/') or not path.endswith('.py'):continue
        tree=ast.parse(git('show','HEAD:'+path))
        for node in ast.walk(tree):
            if isinstance(node,ast.Constant) and isinstance(node.value,str):references.setdefault(node.value,set()).add(path)
    rows=[]
    for path in paths:
        if not path.startswith('src/jarvis/') or not path.endswith('.py'):continue
        tree=ast.parse(git('show','HEAD:'+path))
        for node in ast.walk(tree):
            if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
            for decorator in node.decorator_list:
                if not isinstance(decorator,ast.Call) or not isinstance(decorator.func,ast.Name) or decorator.func.id!='function_tool':continue
                name=next((kw.value.value for kw in decorator.keywords if kw.arg=='name' and isinstance(kw.value,ast.Constant) and isinstance(kw.value.value,str)),None)
                if not name:continue
                families=sorted({part.attr for part in ast.walk(node) if isinstance(part,ast.Attribute) and isinstance(part.value,ast.Name) and part.value.id=='self' and part.attr in CAPABILITIES})
                rows.append({'tool':name,'source':path,'line':node.lineno,'families':families or ['orchestration'],
                             'static_test_references':sorted(references.get(name,[])),
                             'real_world_qualification':'pending','latency_p95_ms':None,'scenario_success_rate':None})
    return {'base_commit':git('rev-parse','HEAD').strip(),'scope':'Committed declarations; no tool is executed. Test references do not establish functional coverage.',
            'declared_tools':len(rows),'family_counts':dict(sorted(Counter(f for r in rows for f in r['families']).items())), 'tools':sorted(rows,key=lambda row:row['tool'])}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    report=inventory();args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'declared_tools':report['declared_tools'],'family_counts':report['family_counts']}))
if __name__=='__main__':main()
