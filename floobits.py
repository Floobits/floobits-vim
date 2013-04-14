# coding: utf-8
import re
import os
import traceback
from urlparse import urlparse

import vim
import dmp_monkey
dmp_monkey.monkey_patch()

from floo import sublime
from floo import AgentConnection
from floo import shared as G
from floo import utils
from floo.vim_protocol import Protocol

G.agent = None

FLOO_BUFS = {}

utils.load_settings()
G.proto = Protocol()

# Vim interface


def global_tick():
    """a hack to make vim evented like"""
    if G.agent:
        G.agent.select()
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
    buf_num = vim.eval("bufnr('%')")
    name = buf.name
    text = buf[:]
    # maybe need win num too?
    oldBuf = FLOO_BUFS.get(buf_num, "")
    if oldBuf != text:
        print "%s changed" % (name)
        FLOO_BUFS[buf_num] = text
        Listener.on_modified(buf_num)


def joinroom(room_url):
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
    G.PROJECT_PATH = os.path.realpath(os.path.join(G.COLAB_DIR, owner, room))
    print 'making dir %s' % G.PROJECT_PATH
    utils.mkdir(G.PROJECT_PATH)

    print("joining room %s" % room_url)

    if G.agent:
        G.agent.stop()
        G.agent = None
    try:
        G.agent = AgentConnection(owner, room, host=parsed_url.hostname, port=port, secure=secure, on_connect=None)
        # owner and room name are slugfields so this should be safe
        Listener.set_agent(G.agent)
        G.agent.connect()
    except Exception as e:
        print(e)
        tb = traceback.format_exc()
        print(tb)

    # thread = threading.Thread(target=run_agent)
    # thread.start()
