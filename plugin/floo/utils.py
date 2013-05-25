import os
import hashlib
import json
import re
from urlparse import urlparse

from lib import diff_match_patch as dmp

import sublime
import msg
import shared as G

per_path = os.path.abspath('persistent.json')


class FlooPatch(object):
    def __init__(self, view):
        self.view = view
        self.buf = view.buf
        self.current = view.get_text()
        self.previous = self.buf['buf']
        self.md5_before = hashlib.md5(self.previous.encode('utf-8')).hexdigest()

    def __str__(self):
        return '%s - %s - %s' % (self.buf['id'], self.buf['path'], self.view.buffer_id())

    def patches(self):
        return dmp.diff_match_patch().patch_make(self.previous, self.current)

    def to_json(self):
        patches = self.patches()
        if len(patches) == 0:
            return None
        msg.debug('sending %s patches' % len(patches))
        patch_str = ''
        for patch in patches:
            patch_str += str(patch)
        return {
            'id': self.buf['id'],
            'md5_after': hashlib.md5(self.current.encode('utf-8')).hexdigest(),
            'md5_before': self.md5_before,
            'path': self.buf['path'],
            'patch': patch_str,
            'name': 'patch'
        }


class edit:
    def __init__(self, view):
        self.view = view

    def __enter__(self):
        self.edit = self.view.begin_edit()
        return self.edit

    def __exit__(self, type, value, traceback):
        self.view.end_edit(self.edit)


def parse_url(room_url):
    secure = G.SECURE
    owner = None
    room_name = None
    parsed_url = urlparse(room_url)
    port = parsed_url.port
    if parsed_url.scheme == 'http':
        if not port:
            port = 3148
        secure = False
    result = re.match('^/r/([-\w]+)/([-\w]+)/?$', parsed_url.path)
    if result:
        (owner, room_name) = result.groups()
    else:
        raise ValueError('%s is not a valid Floobits URL' % room_url)
    return {
        'host': parsed_url.hostname,
        'owner': owner,
        'port': port,
        'room': room_name,
        'secure': secure,
    }


def to_room_url(r):
    port = int(r['port'])
    if r['secure']:
        proto = 'https'
        if port == 3448:
            port = ''
    else:
        proto = 'http'
        if port == 3148:
            port = ''
    if port != '':
        port = ':%s' % port
    room_url = '%s://%s%s/r/%s/%s/' % (proto, r['host'], port, r['owner'], r['room'])
    return room_url


def load_floorc():
    """try to read settings out of the .floorc file"""
    s = {}
    try:
        fd = open(os.path.expanduser('~/.floorc'), 'rb')
    except IOError as e:
        if e.errno == 2:
            return s
        raise

    default_settings = fd.read().split('\n')
    fd.close()

    for setting in default_settings:
        # TODO: this is horrible
        if len(setting) == 0 or setting[0] == '#':
            continue
        try:
            name, value = setting.split(' ', 1)
        except IndexError:
            continue
        s[name.upper()] = value
    return s


def load_settings():
    settings = load_floorc()
    if not settings:
        msg.error('you should probably define some stuff in your ~/.floorc file')
    G.COLAB_DIR = os.path.expanduser(settings.get('share_dir', '~/.floobits/share/'))
    mkdir(G.COLAB_DIR)
    for name, val in settings.items():
        setattr(G, name, val)


def get_room_window():
    room_window = None
    for w in sublime.windows():
        for f in w.folders():
            if f == G.PROJECT_PATH:
                room_window = w
                break
    return room_window


def set_room_window(cb):
    room_window = get_room_window()
    if room_window is None:
        return sublime.set_timeout(lambda: set_room_window(cb), 50)
    G.ROOM_WINDOW = room_window
    cb()


def get_full_path(p):
    full_path = os.path.join(G.PROJECT_PATH, p)
    return unfuck_path(full_path)


def unfuck_path(p):
    return os.path.normcase(os.path.normpath(p))


def to_rel_path(p):
    return os.path.relpath(p, G.PROJECT_PATH).decode('utf-8')


def to_scheme(secure):
    if secure is True:
        return 'https'
    return 'http'


def get_persistent_data():
    try:
        per = open(per_path, 'rb')
    except (IOError, OSError):
        msg.warn('Failed to open %s. Recent room list will be empty.' % per_path)
        return {}
    try:
        persistent_data = json.loads(per.read())
    except:
        msg.warn('Failed to parse %s. Recent room list will be empty.' % per_path)
        return {}
    return persistent_data


def update_persistent_data(data):
    with open(per_path, 'wb') as per:
        per.write(data)


def rm(path):
    """removes path and dirs going up until a OSError"""
    os.remove(path)
    try:
        os.removedirs(os.path.split(path)[0])
    except OSError as e:
        if e.errno != 66:
            msg.error('Can not delete directory {0}.\n{1}'.format(path, e))
            raise


def mkdir(path):
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno != 17:
            msg.error('Can not create directory {0}.\n{1}'.format(path, e))
            raise
