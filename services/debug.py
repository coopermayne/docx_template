"""Debug logging utility for development mode."""

import logging
import time
from functools import wraps
from config import Config

# Create a dedicated debug logger
debug_logger = logging.getLogger('dev_debug')

# Only log if DEV_DEBUG is enabled
if Config.DEV_DEBUG:
    debug_logger.setLevel(logging.DEBUG)
    # Add handler if not already present
    if not debug_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            '\033[36m[DEBUG]\033[0m %(asctime)s - %(message)s',
            datefmt='%H:%M:%S'
        ))
        debug_logger.addHandler(handler)
else:
    debug_logger.setLevel(logging.CRITICAL)  # Effectively disable


def debug_log(message: str, **kwargs):
    """
    Log a debug message only when DEV_DEBUG is enabled.

    Usage:
        debug_log("Processing request", request_id=123, user="john")
    """
    if not Config.DEV_DEBUG:
        return

    if kwargs:
        extras = ' | '.join(f'{k}={v}' for k, v in kwargs.items())
        message = f"{message} | {extras}"

    debug_logger.debug(message)


def debug_timer(func):
    """
    Decorator to time function execution in debug mode.

    Usage:
        @debug_timer
        def my_slow_function():
            ...
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not Config.DEV_DEBUG:
            return func(*args, **kwargs)

        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        debug_log(f"{func.__name__} completed", elapsed=f"{elapsed:.2f}s")
        return result

    return wrapper


class DebugTimer:
    """
    Context manager for timing code blocks in debug mode.

    Usage:
        with DebugTimer("PDF parsing"):
            parse_pdf(file)
    """
    def __init__(self, label: str):
        self.label = label
        self.start = None

    def __enter__(self):
        if Config.DEV_DEBUG:
            self.start = time.time()
            debug_log(f"{self.label} started")
        return self

    def __exit__(self, *args):
        if Config.DEV_DEBUG and self.start:
            elapsed = time.time() - self.start
            debug_log(f"{self.label} completed", elapsed=f"{elapsed:.2f}s")
