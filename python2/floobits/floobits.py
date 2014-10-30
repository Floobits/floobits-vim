# coding: utf-8
import os
import os.path
import webbrowser
import imp
from functools import wraps

try:
    unicode()
except NameError:
    unicode = str

try:
    import urllib
    urllib = imp.reload(urllib)
    from urllib import request
    request = imp.reload(request)
    Request = request.Request
    urlopen = request.urlopen
    HTTPError = urllib.error.HTTPError
    URLError = urllib.error.URLError
    assert Request and urlopen and HTTPError and URLError
except ImportError:
    import urllib2
    urllib2 = imp.reload(urllib2)
    Request = urllib2.Request
    urlopen = urllib2.urlopen
    HTTPError = urllib2.HTTPError
    URLError = urllib2.URLError

vim = None

from floo.common import api, migrations, msg, reactor, utils, shared as G
from floo import editor, vui

VUI = vui.VUI()

reactor = reactor.reactor

# Protocol version
G.__VERSION__ = '0.11'
G.__PLUGIN_VERSION__ = '3.0.5'

utils.reload_settings()

migrations.rename_floobits_dir()
migrations.migrate_symlinks()

def set_globals():
    G.DELETE_LOCAL_FILES = bool(int(vim.eval('floo_delete_local_files')))
    G.SHOW_HIGHLIGHTS = bool(int(vim.eval('floo_show_highlights')))
    G.SPARSE_MODE = bool(int(vim.eval('floo_sparse_mode')))


def _get_line_endings():
    formats = vim.eval('&fileformats')
    if not formats:
        return '\n'
    name = formats.split(',')[0]
    if name == 'dos':
        return '\r\n'
    return '\n'


def info():
    VUI.info()


def vim_choice(prompt, default, choices):
    default = choices.index(default) + 1
    choices_str = '\n'.join(['&%s' % choice for choice in choices])
    try:
        choice = int(vim.eval('confirm("%s", "%s", %s)' % (prompt, choices_str, default)))
    except KeyboardInterrupt:
        return None
    if choice == 0:
        return None
    return choices[choice - 1]


def vim_input(prompt, default, completion=None):
    vim.command('call inputsave()')
    if completion:
        cmd = "let user_input = input('%s', '%s', '%s')" % (prompt, default, completion)
    else:
        cmd = "let user_input = input('%s', '%s')" % (prompt, default)
    vim.command(cmd)
    vim.command('call inputrestore()')
    return vim.eval('user_input')


def global_tick():
    reactor.tick()

def is_connected(warn=False):
    def outer(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            if reactor.is_ready():
                return func(*args, **kwargs)
            if warn:
                msg.error('ignoring request (%s) because you aren\'t in a workspace.' % func.__name__)
            else:
                msg.debug('ignoring request (%s) because you aren\'t in a workspace.' % func.__name__)
        return wrapped
    return outer


@is_connected()
def maybe_selection_changed(ping=False):
    G.AGENT.maybe_selection_changed(vim.current.buffer, ping)


@is_connected()
def maybe_buffer_changed():
    G.AGENT.maybe_buffer_changed(vim.current.buffer)


@is_connected()
def follow(follow_mode=None):
    if follow_mode is None:
        follow_mode = not G.FOLLOW_MODE
    G.FOLLOW_MODE = follow_mode


@is_connected()
def maybe_new_file():
    path = vim.current.buffer.name
    if path is None or path == '':
        msg.debug('get:buf buffer has no filename')
        return None

    if not os.path.exists(path):
        return None
    if not utils.is_shared(path):
        msg.debug('get_buf: %s is not shared' % path)
        return None

    buf = G.AGENT.get_buf_by_path(path)
    if not buf:
        is_dir = os.path.isdir(path)
        if not G.IGNORE:
            msg.warn('G.IGNORE is not set. Uploading anyway.')
            G.AGENT.upload(path)
        if G.IGNORE and G.IGNORE.is_ignored(path, is_dir, True):
            G.AGENT.upload(path)


@is_connected()
def on_save():
    buf = G.AGENT.get_buf_by_path(vim.current.buffer.name)
    if buf:
        G.AGENT.send({
            'name': 'saved',
            'id': buf['id'],
        })


@is_connected(True)
def open_in_browser():
    url = G.AGENT.workspace_url
    webbrowser.open(url)


@is_connected(True)
def add_buf(path=None):
    path = path or vim.current.buffer.name
    G.AGENT._upload(path)


@is_connected(True)
def delete_buf():
    name = vim.current.buffer.name
    G.AGENT.delete_buf(name)


@is_connected()
def buf_enter():
    buf = G.AGENT.get_buf_by_path(vim.current.buffer.name)
    if not buf:
        return
    buf_id = buf['id']
    d = G.AGENT.on_load.get(buf_id)
    if d:
        del G.AGENT.on_load[buf_id]
        try:
            d['patch']()
        except Exception as e:
            msg.debug('Error running on_load patch handler for buf %s: %s' % (buf_id, str(e)))
    # NOTE: we call highlight twice in follow mode... thats stupid
    for user_id, highlight in G.AGENT.user_highlights.items():
        if highlight['id'] == buf_id:
            G.AGENT._on_highlight(highlight)


@is_connected()
def clear():
    buf = G.AGENT.get_buf_by_path(vim.current.buffer.name)
    if not buf:
        return
    view = G.AGENT.get_view(buf['id'])
    if view:
        for user_id, username in G.AGENT.workspace_info['users'].items():
            view.clear_highlight(int(user_id))


@is_connected()
def toggle_highlights():
    G.SHOW_HIGHLIGHTS = not G.SHOW_HIGHLIGHTS
    if G.SHOW_HIGHLIGHTS:
        buf_enter()
        msg.log('Highlights enabled')
        return
    clear()
    msg.log('Highlights disabled')


def share_dir_private(dir_to_share):
    return VUI.share_dir(None, dir_to_share, {'AnonymousUser': []})


def share_dir_public(dir_to_share):
    return VUI.share_dir(None, dir_to_share, {'AnonymousUser': ['view_room']})


def complete_signup():
    msg.debug('Completing signup.')
    if not utils.has_browser():
        msg.log('You need a modern browser to complete the sign up. Go to https://floobits.com to sign up.')
        return
    VUI.pinocchio()


@utils.inlined_callbacks
def check_credentials():
    msg.debug('Print checking credentials.')
    if utils.can_auth():
        return
    if not utils.has_browser():
        msg.log('You need a Floobits account to use the Floobits plugin. Go to https://floobits.com to sign up.')
        return
    yield VUI.create_or_link_account, None, G.DEFAULT_HOST, False


def check_and_join_workspace(workspace_url):
    set_globals()
    try:
        r = api.get_workspace_by_url(workspace_url)
    except Exception as e:
        return editor.error_message('Error joining %s: %s' % (workspace_url, str(e)))
    if r.code >= 400:
        return editor.error_message('Error joining %s: %s' % (workspace_url, r.body))
    msg.debug('Workspace %s exists' % workspace_url)
    return join_workspace(workspace_url)


def join_workspace(workspace_url, d='', upload_path=None):
    editor.line_endings = _get_line_endings()
    cwd = vim.eval('getcwd()')
    if cwd:
        cwd = [cwd]
    else:
        cwd = []
    VUI.join_workspace_by_url(None, workspace_url, cwd)


def part_workspace():
    VUI.part_workspace()


def users_in_workspace():
    if not G.AGENT:
        return msg.warn('Not connected to a workspace.')
    vim.command('echom "Users connected to %s"' % (G.AGENT.workspace,))
    for user in G.AGENT.workspace_info['users'].values():
        vim.command('echom "  %s connected with %s on %s"' % (user['username'], user['client'], user['platform']))


def list_messages():
    if not G.AGENT:
        return msg.warn('Not connected to a workspace.')
    vim.command('echom "Recent messages for %s"' % (G.AGENT.workspace,))
    for message in G.AGENT.get_messages():
        vim.command('echom "  %s"' % (message,))


def say_something():
    if not G.AGENT:
        return msg.warn('Not connected to a workspace.')
    something = vim_input('Say something in %s: ' % (G.AGENT.workspace,), '')
    if something:
        G.AGENT.send_msg(something)
