from functools import wraps
from typing import Callable
from loguru import logger
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)


def retry_with_backoff(max_retries: int = 3):
    """Retry decorator with exponential backoff for async and sync callables"""

    def decorator(func: Callable):
        retrying = retry(
            stop=stop_after_attempt(max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=30),
            retry=retry_if_exception_type((ConnectionError, TimeoutError)),
            reraise=True,
        )

        if asyncio_is_coroutine(func):

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                return await retrying(func)(*args, **kwargs)

            return async_wrapper

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            return retrying(func)(*args, **kwargs)

        return sync_wrapper

    return decorator


def asyncio_is_coroutine(func: Callable) -> bool:
    import inspect
    return inspect.iscoroutinefunction(func)


def log_retry(retry_state):
    """Log retry attempts"""
    logger.warning(
        f"Retrying {retry_state.fn.__name__}: "
        f"attempt {retry_state.attempt_number} "
        f"failed with {retry_state.outcome.exception()}"
    )
