from collections import defaultdict
import time


TIMEOUTS = defaultdict(list)


def windows(*args, **kwargs):
    return []


def set_timeout(func, timeout, *args, **kwargs):
    then = time.time() + (timeout / 1000.0)
    TIMEOUTS[then].append(lambda: func(*args, **kwargs))


def call_timeouts():
    now = time.time()
    to_remove = []
    for t, timeouts in TIMEOUTS.items():
        if now >= t:
            for timeout in timeouts:
                timeout()
            to_remove.append(t)
    for k in to_remove:
        del TIMEOUTS[k]


def error_message(*args, **kwargs):
    print(args, kwargs)


class Region(object):
    def __init__(*args, **kwargs):
        pass
