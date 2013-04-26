# coding: utf-8
import os
import json
import traceback
import urllib2
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


def vim_input(prompt, default):
    vim.command('call inputsave()')
    vim.command("let user_input = input('%s', '%s')" % (prompt, default))
    vim.command('call inputrestore()')
    return vim.eval('user_input')


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


def is_modifiable():
    vim.command("let floo_is_modifiable = 0")
    if not agent or not agent.protocol:
        return
    vim_buf = vim.current.buffer
    if not vim_buf.name:
        return
    if not agent.protocol.is_shared(vim_buf.name):
        return
    if 'patch' not in agent.protocol.perms:
        vim.command("let floo_is_modifiable = 1")


@agent_and_protocol
def maybe_new_file():
    vim_buf = vim.current.buffer
    buf = agent.protocol.get_buf(vim_buf)
    if buf is False:
        agent.protocol.create_buf(vim_buf.name)


def share_dir(dir_to_share):
    dir_to_share = os.path.expanduser(dir_to_share)
    dir_to_share = utils.unfuck_path(dir_to_share)
    room_name = os.path.basename(dir_to_share)
    floo_room_dir = os.path.join(G.COLAB_DIR, G.USERNAME, room_name)

    if os.path.isfile(dir_to_share):
        return msg.error('give me a directory please')

    if not os.path.isdir(dir_to_share):
        return msg.error('The directory %s doesn\'t appear to exist' % dir_to_share)

    floo_file = os.path.join(dir_to_share, '.floo')
    # look for the .floo file for hints about previous behavior
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
            floo_room_dir = os.path.join(G.COLAB_DIR, result['owner'], result['room'])
            # they have previously joined the room
            if os.path.realpath(floo_room_dir) == os.path.realpath(dir_to_share):
                # it could have been deleted, try to recreate it if possible
                # TODO: org or something here?
                if result['owner'] == G.USERNAME:
                    try:
                        api.create_room(room_name)
                        msg.debug('Created room %s' % room_url)
                    except Exception as e:
                        msg.debug('Tried to create room' + str(e))
                # they wanted to share teh dir, so always share it
                return join_room(room_url, lambda x: agent.protocol.create_buf(dir_to_share))

    # link to what they want to share
    try:
        utils.mkdir(os.path.dirname(floo_room_dir))
        os.symlink(dir_to_share, floo_room_dir)
    except OSError as e:
        if e.errno != 17:
            raise
    except Exception as e:
        return msg.error("Couldn't create symlink from %s to %s: %s" % (dir_to_share, floo_room_dir, str(e)))

    # make & join room
    create_room(room_name, dir_to_share)


def create_room(room_name, path=None):
    try:
        api.create_room(room_name)
        room_url = 'https://%s/r/%s/%s' % (G.DEFAULT_HOST, G.USERNAME, room_name)
        msg.debug('Created room %s' % room_url)
    except urllib2.HTTPError as e:
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
    except Exception as e:
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

    try:
        result = utils.parse_url(room_url)
    except Exception as e:
        return msg.error(str(e))

    G.PROJECT_PATH = os.path.realpath(os.path.join(G.COLAB_DIR, result['owner'], result['room']))
    utils.mkdir(os.path.dirname(G.PROJECT_PATH))
    vim.command('cd %s' % G.PROJECT_PATH)

    d = ''
    # TODO: really bad prompt here
    prompt = "Give me a directory to destructively dump data into (or just press enter): "
    if not os.path.isdir(G.PROJECT_PATH):
        while True:
            d = vim_input(prompt, d)
            if d == '':
                utils.mkdir(G.PROJECT_PATH)
                break
            d = os.path.realpath(os.path.expanduser(d))
            if not os.path.isdir(d):
                prompt = '%s is not a directory. Enter an existing path (or press enter): ' % d
                continue
            try:
                os.symlink(d, G.PROJECT_PATH)
                break
            except Exception as e:
                return msg.error("Couldn't create symlink from %s to %s: %s" % (d, G.PROJECT_PATH, str(e)))

    msg.debug("joining room %s" % room_url)

    if agent:
        agent.stop()
    try:
        agent = AgentConnection(on_auth=on_auth, Protocol=Protocol, **result)
        # owner and room name are slugfields so this should be safe
        agent.connect()
    except Exception as e:
        msg.error(str(e))
        tb = traceback.format_exc()
        msg.debug(tb)
        if agent:
            agent.stop()
            agent = None


def part_room():
    if not agent or not agent.stop():
        return msg.warn('Unable to part room: You are not joined to a room.')
    msg.log('You left the room.')
