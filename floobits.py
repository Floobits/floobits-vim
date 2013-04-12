# coding: utf-8
import re
import os
import threading
import time
import traceback
from urlparse import urlparse

import vim

from floo import sublime
from floo import api
from floo import AgentConnection
from floo.listener import Listener
from floo import msg
from floo import shared as G
from floo import utils

agent = None

BUFS = {}

Listener = Listener()


def global_tick():
    global LAST_TIMEOUT
    """a hack to make vim evented like"""
    if agent:
        agent.select()


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


def maybeBufferChanged(*args):
    buf = vim.current.buffer
    buf_num = vim.eval("bufnr('%')")
    name = buf.name
    text = buf[:]
    # maybe need win num too?
    oldBuf = BUFS.get(buf_num, "")
    if oldBuf != text:
        print "%s changed" % (name)
        BUFS[buf_num] = text
        #Listener.on_modified(name)


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
    utils.mkdir(G.PROJECT_PATH)

    def run_agent():
        global agent
        if agent:
            agent.stop()
            agent = None
        try:
            agent = AgentConnection(owner, room, host=parsed_url.hostname, port=port, secure=secure, on_connect=None)
            # owner and room name are slugfields so this should be safe
            Listener.set_agent(agent)
            agent.connect()
        except Exception as e:
            print(e)
            tb = traceback.format_exc()
            print(tb)

    print("joining room %s" % room_url)

    thread = threading.Thread(target=run_agent)
    thread.start()
