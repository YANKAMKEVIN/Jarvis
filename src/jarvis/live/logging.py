import logging


REDACTED_PII_VALUE = "[REDACTED]"


def is_pii_log_field(field: str) -> bool:
    return "pii" in field.split(".")


class LiveKitPIILogFilter(logging.Filter):
    """Redact LiveKit PII extras in local Python logs only.

    LiveKit marks sensitive values with lk.pii.* fields. This filter keeps the
    log record and non-sensitive metadata, but replaces known PII values before
    Python handlers render them. It does not change tool arguments, tool
    results, telemetry payloads, or the diagnostic output rendered by
    `lk agent console`.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        for field in tuple(record.__dict__):
            if is_pii_log_field(field):
                record.__dict__[field] = REDACTED_PII_VALUE

        return True


def install_livekit_pii_log_filter() -> None:
    logger = logging.getLogger("livekit.agents")

    if any(isinstance(item, LiveKitPIILogFilter) for item in logger.filters):
        return

    logger.addFilter(LiveKitPIILogFilter())
