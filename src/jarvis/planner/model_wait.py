"""Bound physical model calls independently of cancelled async missions.

Only inference runs here; native tools must retain their locks until finished.
A late inference cannot execute tools. Its capacity remains occupied until the
provider actually returns, preventing repeated cancellations spawning workers.
"""
from __future__ import annotations

import asyncio
import copy
import threading

_MODEL_SLOTS = threading.BoundedSemaphore(2)


class ModelWaitStopped(Exception):
    def __init__(self, status):
        self.status = status
        super().__init__(status)


async def complete_bounded(model, messages, schemas, cancel, seconds):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(0., seconds)

    def check():
        if cancel.is_set():
            raise ModelWaitStopped('cancelled')
        if loop.time() >= deadline:
            raise ModelWaitStopped('budget_exceeded')

    while True:
        check()
        if _MODEL_SLOTS.acquire(blocking=False):
            break
        await asyncio.sleep(.01)

    done = threading.Event()
    result = []
    try:
        request = copy.deepcopy((messages, schemas))

        def work():
            try:
                result.append((True, model.complete(*request)))
            except BaseException as error:
                result.append((False, error))
            finally:
                _MODEL_SLOTS.release()
                done.set()

        # Does not hold asyncio's default executor (and hence Qt shutdown) open.
        threading.Thread(target=work, name='jarvis-inference', daemon=True).start()
    except BaseException:
        _MODEL_SLOTS.release()
        raise
    while not done.is_set():
        check()
        await asyncio.sleep(.01)
    check()
    success, value = result[0]
    if not success:
        raise value
    return value
