"""Atomic private configuration writes, independently testable without user files."""
import os
import re
import tempfile
from pathlib import Path


def save_api_key(value, root=None):
    value=value.strip()
    if not re.fullmatch(r'[A-Za-z0-9_\-]{20,200}',value):raise ValueError('Format de clé invalide.')
    root=Path(root) if root is not None else Path.home()/'Library/Application Support/Jarvis'
    root.mkdir(parents=True,exist_ok=True);os.chmod(root,0o700)
    path=root/'desktop.env'
    lines=path.read_text().splitlines() if path.exists() else []
    lines=[line for line in lines if not re.match(r'^\s*(?:export\s+)?GOOGLE_API_KEY\s*=',line)]
    lines.append('GOOGLE_API_KEY='+value)
    fd,temporary=tempfile.mkstemp(prefix='.desktop-',dir=root)
    try:
        with os.fdopen(fd,'w') as file:file.write('\n'.join(lines)+'\n')
        os.chmod(temporary,0o600);os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
    os.environ['GOOGLE_API_KEY']=value
    return path
