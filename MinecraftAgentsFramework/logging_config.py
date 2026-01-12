from datetime import datetime, timezone
import logging
import time

class UTCFormatter(logging.Formatter):
    """Custom formatter that uses UTC timezone for all log timestamps."""

    converter = time.gmtime

    def formatTime(self, record, datefmt=None):
        """Format time using UTC with consistent format."""
        ct = datetime.fromtimestamp(record.created, tz=timezone.utc)
        return ct.isoformat() + "Z"


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Configure and return the program logger with console handler."""
    logger = logging.getLogger("MinecraftAgents")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Prevent duplicate handlers if called multiple times
    if logger.handlers:
        return logger

    # Console handler with UTC formatter
    console_formatter = UTCFormatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s"
    )
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(console_formatter)

    logger.addHandler(console_handler)
    logger.info("Logging initialized")

    return logger


def get_logger(name: str = None) -> logging.Logger:
    """Return a child logger with the specified name or the base logger if no name provided."""
    base_logger = logging.getLogger("MinecraftAgents")
    if name:
        return base_logger.getChild(name)
    return base_logger
