# coding: utf-8
import os
import json
import traceback
import urllib2
import atexit
import webbrowser
import subprocess

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

G.DELETE_LOCAL_FILES = bool(vim.eval('floo_delete_local_files'))
G.SHOW_HIGHLIGHTS = bool(vim.eval('floo_show_highlights'))
G.SPARSE_MODE = bool(vim.eval('floo_sparse_mode'))

agent = None
call_feedkeys = False
ticker = None
ticker_errors = 0
using_feedkeys = False

ticker_python = """import sys; import subprocess; import time
args = ['{binary}', '--servername', '{servername}', '--remote-expr', 'g:floobits_global_tick()']
while True:
    time.sleep({sleep})
    # TODO: learn to speak vim or something :(
    proc = subprocess.Popen(args,
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE)
    (stdoutdata, stderrdata) = proc.communicate()
    # # yes, this is stupid...
    if stdoutdata.strip() == '0':
        continue
    if len(stderrdata) == 0:
        continue
    sys.stderr.write(stderrdata)
    sys.exit(1)
"""


def buf_enter():
    pass


def enable_floo_feedkeys():
    global call_feedkeys
    if not using_feedkeys:
        return
    call_feedkeys = True
    vim.command("set updatetime=250")


def disable_floo_feedkeys():
    global call_feedkeys
    if not using_feedkeys:
        return
    call_feedkeys = False
    vim.command("set updatetime=4000")


def fallback_to_feedkeys(warning):
    global using_feedkeys
    using_feedkeys = True
    warning += " Falling back to f//e hack which will break some key commands. You may need to call FlooPause/FlooUnPause before some commands."
    msg.warn(warning)
    enable_floo_feedkeys()


def ticker_watcher(ticker):
    global ticker_errors

    if not agent:
        return
    ticker.poll()
    if ticker.returncode is None:
        return
    msg.warn('respawning new ticker')
    ticker_errors += 1
    if ticker_errors > 10:
        return fallback_to_feedkeys('Too much trouble with the floobits external ticker.')
    start_event_loop()
    sublime.set_timeout(ticker_watcher, 2000, ticker)


def start_event_loop():
    global ticker

    if not bool(int(vim.eval('has("clientserver")'))):
        return fallback_to_feedkeys("This VIM was not compiled with clientserver support. You should consider using a different vim!")

    exe = getattr(G, 'VIM_EXECUTABLE', None)
    if not exe:
        return fallback_to_feedkeys("Your vim was compiled with clientserver, but I don't know the name of the vim executable.  Please define it in your ~/.floorc using the vim_executable directive. e.g. 'vim_executable mvim'.")

    servername = vim.eval("v:servername")
    if not servername:
        return fallback_to_feedkeys('I can not identify the servername of this vim. You may need to pass --servername to vim at startup.')

    evaler = ticker_python.format(binary=exe, servername=servername, sleep='0.2')
    ticker = subprocess.Popen(['python', '-c', evaler],
                              stderr=subprocess.PIPE,
                              stdout=subprocess.PIPE)
    ticker.poll()
    sublime.set_timeout(ticker_watcher, 500, ticker)


def vim_input(prompt, default, completion=""):
    vim.command('call inputsave()')
    vim.command("let user_input = input('%s', '%s', '%s')" % (prompt, default, completion))
    vim.command('call inputrestore()')
    return vim.eval('user_input')


def global_tick():
    """a hack to make vim evented like"""
    if agent:
        agent.tick()
    sublime.call_timeouts()


def cursor_hold():
    global_tick()
    if not call_feedkeys:
        return
    return vim.command("call feedkeys(\"f\\e\", 'n')")


def cursor_holdi():
    global_tick()
    if not call_feedkeys:
        return
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


def is_modifiable(name_to_check=None):
    if not agent or not agent.protocol:
        return
    vim_buf = vim.current.buffer
    name = vim_buf.name
    if not name:
        return
    if name_to_check and name_to_check != name:
        msg.warn('Can not call readonly on file: %s' % name)
    if not agent.protocol.is_shared(name):
        return
    if 'patch' not in agent.protocol.perms:
        vim.command("call g:FlooSetReadOnly()")
        sublime.set_timeout(is_modifiable, 0, name)


@agent_and_protocol
def maybe_new_file():
    vim_buf = vim.current.buffer
    buf = agent.protocol.get_buf(vim_buf)
    if buf is False:
        agent.protocol.create_buf(vim_buf.name)


def share_dir(dir_to_share):
    dir_to_share = os.path.expanduser(dir_to_share)
    dir_to_share = utils.unfuck_path(dir_to_share)
    dir_to_share = os.path.abspath(dir_to_share)

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
    create_room(room_name, floo_room_dir, dir_to_share)


def create_room(room_name, ln_path=None, share_path=None):
    try:
        api.create_room(room_name)
        room_url = 'https://%s/r/%s/%s' % (G.DEFAULT_HOST, G.USERNAME, room_name)
        msg.debug('Created room %s' % room_url)
    except urllib2.HTTPError as e:
        if e.code != 409:
            raise
        if ln_path:
            while True:
                room_name = vim_input('Room %s already exists. Choose another name: ' % room_name, room_name + "1")
                new_path = os.path.join(os.path.dirname(ln_path), room_name)
                try:
                    os.rename(ln_path, new_path)
                except OSError:
                    continue
                msg.debug('renamed ln %s to %s' % (ln_path, new_path))
                ln_path = new_path
                break

        return create_room(room_name, ln_path, share_path)
    except Exception as e:
        sublime.error_message('Unable to create room: %s' % str(e))
        return

    try:
        webbrowser.open(room_url + '/settings', new=2, autoraise=True)
    except Exception:
        msg.debug("Couldn't open a browser. Thats OK!")
    join_room(room_url, lambda x: agent.protocol.create_buf(share_path))


@agent_and_protocol
def add_buf(path=None):
    path = path or vim.current.buffer.name
    agent.protocol.create_buf(path, True)


@agent_and_protocol
def delete_buf():
    name = vim.current.buffer.name
    agent.protocol.delete_buf(name)


def stop_everything():
    global agent
    if agent:
        agent.stop()
        agent = None
    if ticker:
        ticker.kill()
    disable_floo_feedkeys()
    #TODO: get this value from vim and reset it
    vim.command("set updatetime=4000")
#NOTE: not strictly necessary
atexit.register(stop_everything)


def join_room(room_url, on_auth=None):
    global agent
    msg.debug("room url is %s" % room_url)

    try:
        result = utils.parse_url(room_url)
    except Exception as e:
        return msg.error(str(e))

    G.PROJECT_PATH = os.path.realpath(os.path.join(G.COLAB_DIR, result['owner'], result['room']))
    utils.mkdir(os.path.dirname(G.PROJECT_PATH))

    d = ''
    # TODO: really bad prompt here
    prompt = "Give me a directory to sync data to (or just press enter): "
    if not os.path.isdir(G.PROJECT_PATH):
        while True:
            d = vim_input(prompt, d, "dir")
            if d == '':
                utils.mkdir(G.PROJECT_PATH)
                break
            d = os.path.realpath(os.path.expanduser(d))
            if os.path.isfile(d):
                prompt = '%s is not a directory. Enter an existing path (or press enter): ' % d
                continue
            if not os.path.isdir(d):
                try:
                    utils.mkdir(d)
                except Exception as e:
                    prompt = "Couldn't make dir: %s because %s " % (d, str(e))
                    continue
            try:
                os.symlink(d, G.PROJECT_PATH)
                break
            except Exception as e:
                return msg.error("Couldn't create symlink from %s to %s: %s" % (d, G.PROJECT_PATH, str(e)))

    G.PROJECT_PATH = os.path.realpath(G.PROJECT_PATH + os.sep)
    vim.command('cd %s' % G.PROJECT_PATH)
    msg.debug("joining room %s" % room_url)

    stop_everything()
    try:
        start_event_loop()
        agent = AgentConnection(on_auth=on_auth, Protocol=Protocol, **result)
        # owner and room name are slugfields so this should be safe
        agent.connect()
    except Exception as e:
        msg.error(str(e))
        tb = traceback.format_exc()
        msg.debug(tb)
        stop_everything()


def part_room():
    if not agent:
        return msg.warn('Unable to part room: You are not joined to a room.')
    stop_everything()
    msg.log('You left the room.')
