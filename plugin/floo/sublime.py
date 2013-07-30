import sys
from collections import defaultdict
import time


timeouts = defaultdict(list)


def windows(*args, **kwargs):
    return []


def set_timeout(func, timeout):
    then = time.time() + (timeout / 1000.0)
    timeouts[then].append(func)


def call_timeouts():
    now = time.time()
    to_remove = []
    for t, tos in timeouts.items():
        if now >= t:
            for timeout in tos:
                timeout()
            to_remove.append(t)
    for k in to_remove:
        del timeouts[k]


def error_message(*args, **kwargs):
    print(args, kwargs)


class Region(object):
    def __init__(*args, **kwargs):
        pass


def platform():
    return sys.platform
