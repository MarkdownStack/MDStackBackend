"""Logging configuration — new; there was no explicit setup before this
(the app relied on Python's bare root-logger default).

Called once from main.py's create_app(). ``disable_existing_loggers=False``
is deliberate: dictConfig tears down every logger that already exists by
the time it runs unless told not to — without this, uvicorn's own
``uvicorn``/``uvicorn.access``/``uvicorn.error`` loggers would lose their
handlers and access logging would silently go quiet.
"""

import logging.config


def configure_logging(log_level: str = "INFO") -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)s %(name)s: %(message)s",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                },
            },
            "root": {
                "level": log_level,
                "handlers": ["console"],
            },
        }
    )
