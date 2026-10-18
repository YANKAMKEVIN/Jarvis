"""Session-owned, reentrant desktop lease and cancellable FIFO waiting."""
import asyncio
from contextlib import asynccontextmanager


class WaitingCancelled(Exception):
    pass


@asynccontextmanager
async def acquire(resource, cancel=None):
    waiter = asyncio.create_task(resource.acquire())
    acquired = False
    try:
        while not waiter.done():
            if cancel is not None and cancel.is_set():
                raise WaitingCancelled()
            await asyncio.wait({waiter}, timeout=0.05)
        acquired = waiter.result()
        if cancel is not None and cancel.is_set():
            raise WaitingCancelled()
        yield
    finally:
        if not waiter.done():
            waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)
        if not acquired and not waiter.cancelled() and waiter.exception() is None:
            acquired = waiter.result()
        if acquired:
            resource.release()


class DesktopGate:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.owner = None

    @property
    def owned(self):
        return self.owner is asyncio.current_task()

    @property
    def busy(self):
        return self.lock.locked()

    @asynccontextmanager
    async def hold(self, cancel=None):
        if self.owned:
            yield
            return
        async with acquire(self.lock, cancel):
            self.owner = asyncio.current_task()
            try:
                yield
            finally:
                self.owner = None
