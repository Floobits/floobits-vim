# coding: utf-8
import vim
import re
import os
import threading
import traceback
from urlparse import urlparse

import sublime

from floo import api
from floo import AgentConnection
from floo.listener import Listener
from floo import msg
from floo import shared as G
from floo import utils


agent = None

def handle_shit(*args, **kwargs):
    global b1
    currentBuffer = vim.current.buffer


def run_agent(owner, room, host, port, secure):
    global agent
    if agent:
        agent.stop()
        agent = None
    try:
        agent = AgentConnection(owner, room, host=host, port=port, secure=secure, on_connect=None)
        # owner and room name are slugfields so this should be safe
        Listener.set_agent(agent)
        agent.connect()
    except Exception as e:
        print(e)
        tb = traceback.format_exc()
        print(tb)


def joinroom(room_url):
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

    thread = threading.Thread(target=run_agent, kwargs={
        'owner': owner,
        'room': room,
        'host': parsed_url.hostname,
        'port': port,
        'secure': secure,
    })
    thread.start()
