# Loguru Logging

This project uses [loguru](https://loguru.readthedocs.io/) as the sole logging library. Never use `print` or stdlib `logging`.

## Basic Usage

```python
from loguru import logger

logger.debug("Debug message")
logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message")
logger.critical("Critical message")
```

## Structured Logging

```python
logger.info("User created", user_id=42, email="user@example.com")
logger.error("Request failed", status_code=500, url="/api/data")
```

## Exception Logging

```python
try:
    risky_operation()
except ValueError as e:
    logger.exception("Operation failed")   # logs with full traceback
    # or
    logger.error("Operation failed: {}", e)
```

## Configuration

Configure once at the entrypoint (`main.py`), never in library code:

```python
from loguru import logger
import sys

# Remove default handler, add custom one
logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{line} | {message}",
)

# Optional: also log to file
logger.add(
    "logs/app.log",
    rotation="10 MB",
    retention="7 days",
    level="DEBUG",
)
```

## Library Code Rule

In library code (`python_repo_template/`), **never configure the logger**. Just import and use it:

```python
from loguru import logger

def my_function() -> None:
    logger.debug("Processing...")
```

The application entrypoint controls the output. By default loguru is silent in libraries that haven't configured it, which is correct behaviour.

## Testing with Loguru

```python
def test_logs_warning(caplog):
    # Use loguru's caplog integration or check side effects
    with caplog.at_level("WARNING"):
        my_function_that_warns()
    assert "expected message" in caplog.text
```

## Anti-Patterns

```python
# NEVER do this
print("debug info")
import logging; logging.info("message")

# NEVER configure logger in library code
logger.add(sys.stderr)  # wrong in python_repo_template/

# ALWAYS do this
from loguru import logger
logger.info("message")
```
