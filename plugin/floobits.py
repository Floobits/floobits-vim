# coding: utf-8
import re
import os
import traceback
from urlparse import urlparse

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
if floo_log_level:
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
            func(*args, **kwargs)
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


@agent_and_protocol
def create_room(room_name):
    try:
        api.create_room(room_name)
        room_url = 'https://%s/r/%s/%s' % (G.DEFAULT_HOST, G.USERNAME, room_name)
        msg.log('Created room %s' % room_url)
    except Exception as e:
        msg.error('Unable to create room: %s' % str(e))
        return

    join_room(room_url)


@agent_and_protocol
def delete_buf():
    name = vim.current.buffer.name
    agent.protocol.delete_buf(name)


def join_room(room_url):
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
        agent = AgentConnection(owner, room, host=parsed_url.hostname, port=port, secure=secure, on_auth=None, Protocol=Protocol)
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
