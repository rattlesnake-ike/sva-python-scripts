"""Shared HTTP helper: one requests.Session per worker thread.

A search fans out across many (source, query) pairs on a thread pool. Reusing
a Session per thread keeps TLS connections alive between the queries that land
on the same thread, which trims latency on repeat searches. A Session is not
thread-safe, so each thread gets its own — never a pool shared across threads.
"""
import threading

import requests

_local = threading.local()


def get(url, **kwargs):
    """Thread-local Session.get(): same signature and return value as
    requests.get()."""
    session = getattr(_local, "session", None)
    if session is None:
        session = requests.Session()
        _local.session = session
    return session.get(url, **kwargs)
