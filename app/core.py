import random

from loguru import logger


def add_random_offset(value: int, max_offset: int = 100) -> int:
    """Return value plus a random integer in [0, max_offset]."""
    offset = random.randint(0, max_offset)
    logger.debug(
        "add_random_offset({}, max_offset={}) -> {}", value, max_offset, value + offset
    )
    return value + offset
