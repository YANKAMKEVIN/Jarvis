"""Bounded, deduplicated local notices; no transcripts or model-generated markup."""
from collections import deque
from dataclasses import dataclass
from time import monotonic

@dataclass(frozen=True)
class Notice:
    key: str
    text: str
    mission_id: str | None = None
    destination: str = 'missions'
    created: float = 0

class NoticeQueue:
    def __init__(self,clock=monotonic):
        self.clock=clock
        self.pending=deque(maxlen=5)
        self.seen=deque(maxlen=128)
    def put(self,key,text,mission_id=None,destination='missions'):
        now=self.clock()
        if any(item==key and now-created<60 for item,created in self.seen): return False
        self.seen.append((key,now))
        self.pending.append(Notice(key,text[:240],mission_id,destination,self.clock()))
        return True
    def take(self):
        while self.pending:
            notice=self.pending.popleft()
            if self.clock()-notice.created < 60: return notice
        return None
