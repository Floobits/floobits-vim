import sys
from collections import defaultdict
import time

import vim

try:
    from .common import shared as G
except (ImportError, ValueError):
    import common.shared as G


timeouts = defaultdict(list)
top_timeout_id = 0
cancelled_timeouts = set()
calling_timeouts = False


def windows(*args, **kwargs):
    return []


def set_timeout(func, timeout, *args, **kwargs):
    global top_timeout_id
    timeout_id = top_timeout_id
    top_timeout_id + 1
    if top_timeout_id > 100000:
        top_timeout_id = 0

    def timeout_func():
        if timeout_id in cancelled_timeouts:
            cancelled_timeouts.remove(timeout_id)
            return
        func(*args, **kwargs)

    then = time.time() + (timeout / 1000.0)
    timeouts[then].append(timeout_func)
    return timeout_id


def cancel_timeout(timeout_id):
    if timeout_id in timeouts:
        cancelled_timeouts.add(timeout_id)


def call_timeouts():
    global calling_timeouts
    if calling_timeouts:
        return
    calling_timeouts = True
    now = time.time()
    to_remove = []
    for t, tos in timeouts.items():
        if now >= t:
            for timeout in tos:
                timeout()
            to_remove.append(t)
    for k in to_remove:
        del timeouts[k]
    calling_timeouts = False


def error_message(*args, **kwargs):
    editor = getattr(G, 'editor', None)
    if editor:
        editor.error_message(*args, **kwargs)
    else:
        print(args, kwargs)


def status_message(msg):
    editor = getattr(G, 'editor', None)
    if editor:
        editor.status_message(msg)
    else:
        print(msg)


def vim_choice(prompt, default, choices):
    default = choices.index(default) + 1
    choices_str = '\n'.join(['&%s' % choice for choice in choices])
    try:
        choice = int(vim.eval('confirm("%s", "%s", %s)' % (prompt, choices_str, default)))
    except KeyboardInterrupt:
        return None
    if choice == 0:
        return None
    return choices[choice - 1]


def ok_cancel_dialog(prompt):
    choice = vim_choice(prompt, 'ok', ['ok', 'cancel'])
    return choice == 'ok'


def open_file(file):
    raise NotImplementedError('open_file')


def platform():
    return sys.platform
