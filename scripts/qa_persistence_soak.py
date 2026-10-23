"""Exercise real local persistence repeatedly, with simulated notification output.

No microphone, GUI, network or user stores. This is local-storage endurance,
not a qualification of a complete voice session. Latencies cover a local cycle.
"""
import argparse
from collections import deque
from contextlib import closing
import json
import math
import os
from pathlib import Path
import statistics
import sys
import tempfile
import threading
import time
import tracemalloc
import sqlite3

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from jarvis.capabilities.notes import NotesCapability
from jarvis.schedule.reminders import ReminderStore, deliver_reminders


def fd_count():
    directory = Path('/dev/fd')
    return len(list(directory.iterdir())) if directory.exists() else None


def run(seconds, interval):
    samples = deque(maxlen=2048)
    tracemalloc.start()
    initial_threads = threading.active_count()
    initial_fds = fd_count()
    initial_memory = None
    cycles = failures = 0
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='jarvis-storage-soak-') as root:
        root = Path(root)
        store = ReminderStore(root/'reminders.db')
        notes = NotesCapability(root/'notes')
        name = None
        while time.monotonic()-started < seconds:
            begin = time.perf_counter()
            if cycles % 200 == 0:
                if name:
                    (root/'notes'/name).unlink()
                saved = notes.save_note('QA initial content', 'Soak')
                assert saved.ok
                name = Path(saved.data['path']).name
            token = f'QA cycle {cycles}'
            assert notes.append_note(name, token).ok
            assert token in (root/'notes'/name).read_text()
            row = store.add(token, 100)
            # Every tenth pass injects a notifier rejection and checks recovery
            # through a newly constructed store rather than reused state.
            if cycles % 10 == 0:
                assert deliver_reminders(store, now=200, notifier=lambda _: False) == []
                assert ReminderStore(store.path).get(row['id'])['status'] == 'pending'
                failures += 1
            seen = []
            assert deliver_reminders(ReminderStore(store.path), now=201, notifier=seen.append) == [row['id']]
            assert seen == [f'Rappel : {token}']
            assert deliver_reminders(store, now=202, notifier=seen.append) == []
            # Independent SQL observation, not the capability's own success flag.
            with closing(sqlite3.connect(store.path)) as conn:
                assert conn.execute('SELECT status FROM reminders WHERE id=?', (row['id'],)).fetchone() == ('done',)
            cycles += 1
            samples.append((time.perf_counter()-begin)*1000)
            if cycles == 20:
                initial_memory = tracemalloc.get_traced_memory()[0]
            if interval:
                time.sleep(interval)
        elapsed = time.monotonic()-started
        retained, peak = tracemalloc.get_traced_memory()
        disk_bytes = sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
        final_fds = fd_count()
        final_threads = threading.active_count()
    tracemalloc.stop()
    memory_growth = retained-initial_memory if initial_memory is not None else None
    ordered = sorted(samples)
    checks = {'cycles_executed': cycles > 0,
              'threads_bounded': final_threads <= initial_threads+2,
              'fds_bounded': initial_fds is None or final_fds <= initial_fds+4,
              'python_retained_memory_bounded': memory_growth is None or memory_growth < 10*1024*1024}
    return {'backend': 'Real isolated SQLite and Markdown; notification callbacks simulated',
            'scope': 'Local persistence only; not full voice/hardware endurance',
            'requested_seconds': seconds, 'elapsed_seconds': round(elapsed,3),
            'two_hour_storage_run': elapsed >= 7200,
            'cycles': cycles, 'notification_failures_injected_and_recovered': failures,
            'latency_sample': {'window': 'last 2048 local cycles, includes fault/retry cycles; excludes pacing',
                'count': len(samples), 'median_ms': round(statistics.median(samples),3),
                'p95_ms': round(ordered[max(0,math.ceil(len(ordered)*.95)-1)],3)},
            'resources': {'fds_before':initial_fds,'fds_after':final_fds,
                'threads_before':initial_threads,'threads_after':final_threads,
                'python_retained_growth_after_warmup_bytes':memory_growth,
                'python_peak_bytes':peak,'database_and_note_bytes':disk_bytes},
            'checks': checks, 'passed': all(checks.values())}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=float,default=60)
    parser.add_argument('--interval',type=float,default=.05)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not 0 < args.seconds <= 86400 or not 0 <= args.interval <= 10:
        parser.error('seconds must be in (0,86400], interval in [0,10]')
    result=run(args.seconds,args.interval)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
