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
from floo import shared as G
from floo import utils
from floo.vim_protocol import Protocol

utils.load_settings()
# Vim interface
agent = None


def global_tick():
    """a hack to make vim evented like"""
    if agent:
        agent.tick()
    sublime.call_timeouts()


def CursorHold(*args, **kwargs):
    global_tick()
    vim.command("call feedkeys(\"f\e\",'n')")


def CursorHoldI(*args, **kwargs):
    global_tick()
    linelen = int(vim.eval("col('$')-1"))
    if linelen > 0:
        if int(vim.eval("col('.')")) == 1:
            vim.command("call feedkeys(\"\<Right>\<Left>\",'n')")
        else:
            vim.command("call feedkeys(\"\<Left>\<Right>\",'n')")
    else:
        vim.command("call feedkeys(\"\ei\",'n')")


def maybeBufferChanged():
    buf = vim.current.buffer
    agent.protocol.maybe_changed(buf)


def joinroom(room_url):
    global agent
    print("room url is %s" % room_url)
    secure = G.SECURE
    parsed_url = urlparse(room_url)
    port = parsed_url.port
    if parsed_url.scheme == 'http':
        if not port:
            port = 3148
        secure = False
    result = re.match('^/r/([-\w]+)/([-\w]+)/?$', parsed_url.path)
    if not result:
        return sublime.error_message('Unable to parse your URL!')

    (owner, room) = result.groups()
    G.PROJECT_PATH = os.path.realpath(os.path.expanduser(os.path.join(G.COLAB_DIR, owner, room)))
    print("making dir %s" % G.PROJECT_PATH)
    utils.mkdir(G.PROJECT_PATH)

    print("joining room %s" % room_url)

    if agent:
        agent.stop()
    try:
        agent = AgentConnection(owner, room, host=parsed_url.hostname, port=port, secure=secure, on_auth=None, Protocol=Protocol)
        # owner and room name are slugfields so this should be safe
        agent.connect()
    except Exception as e:
        print(e)
        tb = traceback.format_exc()
        print(tb)

    # thread = threading.Thread(target=run_agent)
    # thread.start()
