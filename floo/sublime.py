import time


def windows(*args, **kwargs):
    return []


def set_timeout(func, timeout):
    time.sleep(timeout)
    func()


def load_settings(*args, **kwargs):
    # TODO: read these from ~/.floorc
    settings = {
        "username": "testing",
        "secret": "testing",
        "debug": True,
    }
    return settings


def error_message(*args, **kwargs):
    print(args, kwargs)


class Region(object):
    def __init__(*args, **kwargs):
        pass
