# coding: utf-8
import re
import os
import json
import traceback
import urllib2
from urlparse import urlparse
import webbrowser

import vim
from floo import dmp_monkey
dmp_monkey.monkey_patch()

from floo import sublime
from floo import AgentConnection
from floo import msg
from floo import shared as G
from floo import utils
from floo import api
from floo.vim_protocol import Protocol


utils.load_settings()

# enable debug with let floo_log_level = 'debug'
floo_log_level = vim.eval('floo_log_level')
msg.LOG_LEVEL = msg.LOG_LEVELS.get(floo_log_level.upper(), msg.LOG_LEVELS['MSG'])

agent = None


def global_tick():
    """a hack to make vim evented like"""
    if agent:
        agent.tick()
    sublime.call_timeouts()


def cursor_hold(*args, **kwargs):
    global_tick()
    vim.command('call feedkeys("f\\e", "n")')


def cursor_holdi(*args, **kwargs):
    global_tick()
    linelen = int(vim.eval("col('$')-1"))
    if linelen > 0:
        if int(vim.eval("col('.')")) == 1:
            vim.command("call feedkeys(\"\<Right>\<Left>\",'n')")
        else:
            vim.command("call feedkeys(\"\<Left>\<Right>\",'n')")
    else:
        vim.command("call feedkeys(\"\ei\",'n')")


def agent_and_protocol(func):
    def wrapped(*args, **kwargs):
        if agent and agent.protocol:
            return func(*args, **kwargs)
        msg.debug('ignoring request becuase there is no agent: %s' % func.__name__)
    return wrapped


@agent_and_protocol
def maybe_selection_changed(ping=False):
    agent.protocol.maybe_selection_changed(vim.current.buffer, ping)


@agent_and_protocol
def maybe_buffer_changed():
    agent.protocol.maybe_buffer_changed(vim.current.buffer)


@agent_and_protocol
def follow(follow_mode=None):
    agent.protocol.follow(follow_mode)


@agent_and_protocol
def maybe_new_file():
    vim_buf = vim.current.buffer
    buf = agent.protocol.get_buf(vim_buf)
    if buf is False:
        agent.protocol.create_buf(vim_buf.name)


def share_dir(path):
    path = os.path.expanduser(path)
    path = utils.unfuck_path(path)
    room_name = os.path.basename(path)
    maybe_shared_dir = os.path.join(G.COLAB_DIR, G.USERNAME, room_name)

    if os.path.isfile(path):
        return msg.error('give me a directory please')

    if not os.path.isdir(path):
        return msg.error('The directory %s doesn\'t appear to exist' % path)

    floo_file = os.path.join(path, '.floo')

    info = {}
    try:
        floo_info = open(floo_file, 'rb').read().decode('utf-8')
        info = json.loads(floo_info)
    except (IOError, OSError):
        pass
    except Exception:
        msg.warn("couldn't read the floo_info file: %s" % floo_file)

    room_url = info.get('url')
    if room_url:
        try:
            result = utils.parse_url(room_url)
        except Exception as e:
            msg.error(str(e))
        else:
            room_name = result['room']
            maybe_shared_dir = os.path.join(G.COLAB_DIR, result['owner'], result['room'])
            if os.path.realpath(maybe_shared_dir) == os.path.realpath(path):
                return join_room(room_url)

    # go make sym link
    try:
        utils.mkdir(os.path.dirname(maybe_shared_dir))
        os.symlink(path, maybe_shared_dir)
    except OSError as e:
        if e.errno != 17:
            raise
    except Exception as e:
        return msg.error("Couldn't create symlink from %s to %s: %s" % (path, maybe_shared_dir, str(e)))

    # make & join room
    create_room(room_name, maybe_shared_dir)


def vim_input(prompt, default):
    vim.command('call inputsave()')
    vim.command("let user_input = input('%s', '%s')" % (prompt, default))
    vim.command('call inputrestore()')
    return vim.eval('user_input')


def create_room(room_name, path=None):
    try:
        api.create_room(room_name)
        room_url = 'https://%s/r/%s/%s' % (G.DEFAULT_HOST, G.USERNAME, room_name)
        msg.debug('Created room %s' % room_url)
    except urllib2.HTTPError, e:
        if e.code != 409:
            raise
        if path:
            while True:
                room_name = vim_input('Room %s already exists. Choose another name: ' % room_name, room_name + "1")
                new_path = os.path.join(os.path.dirname(path), room_name)
                try:
                    os.rename(path, new_path)
                except OSError:
                    continue
                path = new_path
                break

        return create_room(room_name, path)
    except urllib2.URLError, e:
        sublime.error_message('Unable to create room: %s' % str(e))
        return

    try:
        webbrowser.open(room_url + '/settings', new=2, autoraise=True)
    except Exception:
        msg.debug("Couldn't open a browser. Thats OK!")
    join_room(room_url, lambda x: agent.protocol.create_buf(path))


@agent_and_protocol
def delete_buf():
    name = vim.current.buffer.name
    agent.protocol.delete_buf(name)


def join_room(room_url, on_auth=None):
    global agent
    msg.debug("room url is %s" % room_url)
    secure = G.SECURE
    parsed_url = urlparse(room_url)
    port = parsed_url.port
    if parsed_url.scheme == 'http':
        if not port:
            port = 3148
        secure = False
    result = re.match('^/r/([-\w]+)/([-\w]+)/?$', parsed_url.path)
    if not result:
        return msg.error('Unable to parse your URL!')

    (owner, room) = result.groups()
    G.PROJECT_PATH = os.path.realpath(os.path.join(G.COLAB_DIR, owner, room))
    msg.debug("making dir %s" % G.PROJECT_PATH)
    utils.mkdir(G.PROJECT_PATH)

    msg.debug("joining room %s" % room_url)

    if agent:
        agent.stop()
    try:
        agent = AgentConnection(owner, room, host=parsed_url.hostname, port=port, secure=secure, on_auth=on_auth, Protocol=Protocol)
        # owner and room name are slugfields so this should be safe
        agent.connect()
    except Exception as e:
        msg.debug(e)
        tb = traceback.format_exc()
        msg.debug(tb)


def part_room():
    if not agent or not agent.stop():
        return msg.warn('Unable to part room: You are not joined to a room.')
    msg.log('You left the room.')
