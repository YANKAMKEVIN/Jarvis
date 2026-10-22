"""Per-request document consent; asyncio.to_thread carries context automatically."""
from contextvars import ContextVar
REMOTE_DOCUMENT_PERMISSION=ContextVar('jarvis_remote_document_permission',default=None)
