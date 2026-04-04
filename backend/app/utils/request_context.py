"""Request context propagation via contextvars.

Provides a request_id context variable that is set by the logging middleware
and can be read by any service-layer code to correlate logs across a request.
"""

import contextvars
import logging

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default=""
)


class RequestIdFilter(logging.Filter):
    """Logging filter that adds request_id to log records from the context var."""

    def filter(self, record):
        record.request_id = request_id_var.get("")
        return True
