# coding: utf-8
import os
import os.path
import traceback
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

import vim

from floo.common import api, ignore, migrations, msg, reactor, utils, shared as G
from floo.common.handlers.account import CreateAccountHandler
from floo.common.handlers.credentials import RequestCredentialsHandler
from floo import editor, vui

VUI = vui.VUI()

reactor = reactor.reactor

# Protocol version
G.__VERSION__ = '0.11'
G.__PLUGIN_VERSION__ = '3.0.0'

utils.reload_settings()

migrations.rename_floobits_dir()
migrations.migrate_symlinks()

G.DELETE_LOCAL_FILES = bool(int(vim.eval('floo_delete_local_files')))
G.SHOW_HIGHLIGHTS = bool(int(vim.eval('floo_show_highlights')))
G.SPARSE_MODE = bool(int(vim.eval('floo_sparse_mode')))
G.TIMERS = bool(int(vim.eval('has("timers")')))


def _get_line_endings():
    formats = vim.eval('&fileformats')
    if not formats:
        return '\n'
    name = formats.split(',')[0]
    if name == 'dos':
        return '\r\n'
    return '\n'


def floobits_info():
    VUI.floobits_info()


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


def floobits_pause():
    return vui.floobits_pause()


def floobits_unpause():
    return vui.floobits_unpause()


def floobits_global_tick():
    reactor.tick()


def floobits_cursor_hold():
    floobits_global_tick()
    if not vui.call_feedkeys:
        return
    return vim.command("call feedkeys(\"f\\e\", 'n')")


def floobits_cursor_holdi():
    floobits_global_tick()
    if not vui.call_feedkeys:
        return
    linelen = int(vim.eval("col('$')-1"))
    if linelen > 0:
        if int(vim.eval("col('.')")) == 1:
            vim.command("call feedkeys(\"\<Right>\<Left>\",'n')")
        else:
            vim.command("call feedkeys(\"\<Left>\<Right>\",'n')")
    else:
        vim.command("call feedkeys(\"\ei\",'n')")


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
def floobits_maybe_selection_changed(ping=False):
    G.AGENT.maybe_selection_changed(vim.current.buffer, ping)


@is_connected()
def floobits_maybe_buffer_changed():
    G.AGENT.maybe_buffer_changed(vim.current.buffer)


@is_connected()
def floobits_follow(follow_mode=None):
    if follow_mode is None:
        follow_mode = not G.FOLLOW_MODE
    G.FOLLOW_MODE = follow_mode


@is_connected()
def floobits_maybe_new_file():
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
        if not ignore.is_ignored(path):
            G.AGENT.upload(path)


@is_connected()
def floobits_on_save():
    buf = G.AGENT.get_buf_by_path(vim.current.buffer.name)
    if buf:
        G.AGENT.send({
            'name': 'saved',
            'id': buf['id'],
        })


@is_connected(True)
def floobits_open_in_browser():
    url = G.AGENT.workspace_url
    webbrowser.open(url)


@is_connected(True)
def floobits_add_buf(path=None):
    path = path or vim.current.buffer.name
    G.AGENT._upload(path)


@is_connected(True)
def floobits_delete_buf():
    name = vim.current.buffer.name
    G.AGENT.delete_buf(name)


@is_connected()
def floobits_buf_enter():
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
def floobits_clear():
    buf = G.AGENT.get_buf_by_path(vim.current.buffer.name)
    if not buf:
        return
    view = G.AGENT.get_view(buf['id'])
    if view:
        for user_id, username in G.AGENT.workspace_info['users'].items():
            view.clear_highlight(int(user_id))


@is_connected()
def floobits_toggle_highlights():
    G.SHOW_HIGHLIGHTS = not G.SHOW_HIGHLIGHTS
    if G.SHOW_HIGHLIGHTS:
        floobits_buf_enter()
        msg.log('Highlights enabled')
        return
    floobits_clear()
    msg.log('Highlights disabled')


def floobits_share_dir_private(dir_to_share):
    return VUI.share_dir(None, dir_to_share, {'AnonymousUser': []})


def floobits_share_dir_public(dir_to_share):
    return VUI.share_dir(None, dir_to_share, {'AnonymousUser': ['view_room']})


def floobits_complete_signup():
    msg.debug('Completing signup.')
    if not utils.has_browser():
        msg.log('You need a modern browser to complete the sign up. Go to https://floobits.com to sign up.')
        return
    vui.pinocchio()


def floobits_check_credentials():
    msg.debug('Print checking credentials.')
    if utils.can_auth():
        return
    if not utils.has_browser():
        msg.log('You need a Floobits account to use the Floobits plugin. Go to https://floobits.com to sign up.')
        return
    floobits_setup_credentials()


def floobits_setup_credentials():
    prompt = 'You need a Floobits account! Do you have one? If not, we will create one for you [y/n]. '
    d = vim_input(prompt, '')
    if d and (d != 'y' and d != 'n'):
        return floobits_setup_credentials()
    agent = None
    if d == 'y':
        msg.debug('You have an account.')
        agent = RequestCredentialsHandler()
    elif not utils.get_persistent_data().get('disable_account_creation'):
        agent = CreateAccountHandler()
    if not agent:
        msg.error('A configuration error occured earlier. Please go to floobits.com and sign up to use this plugin.\n\n'
                  'We\'re really sorry. This should never happen.')
        return
    try:
        reactor.connect(agent, G.DEFAULT_HOST, G.DEFAULT_PORT, True)
    except Exception as e:
        msg.error(str(e))
        msg.debug(traceback.format_exc())


def floobits_check_and_join_workspace(workspace_url):
    try:
        r = api.get_workspace_by_url(workspace_url)
    except Exception as e:
        return editor.error_message('Error joining %s: %s' % (workspace_url, str(e)))
    if r.code >= 400:
        return editor.error_message('Error joining %s: %s' % (workspace_url, r.body))
    msg.debug('Workspace %s exists' % workspace_url)
    return floobits_join_workspace(workspace_url)


def floobits_join_workspace(workspace_url, d='', upload_path=None):
    editor.line_endings = _get_line_endings()
    cwd = vim.eval('getcwd()')
    if cwd:
        cwd = [cwd]
    else:
        cwd = []
    VUI.join_workspace_by_url(None, workspace_url, cwd)


def floobits_part_workspace():
    VUI.floobits_part_workspace()


def floobits_users_in_workspace():
    if not G.AGENT:
        return msg.warn('Not connected to a workspace.')
    vim.command('echom "Users connected to %s"' % (G.AGENT.workspace,))
    for user in G.AGENT.workspace_info['users'].values():
        vim.command('echom "  %s connected with %s on %s"' % (user['username'], user['client'], user['platform']))


def floobits_list_messages():
    if not G.AGENT:
        return msg.warn('Not connected to a workspace.')
    vim.command('echom "Recent messages for %s"' % (G.AGENT.workspace,))
    for message in G.AGENT.get_messages():
        vim.command('echom "  %s"' % (message,))


def floobits_say_something():
    if not G.AGENT:
        return msg.warn('Not connected to a workspace.')
    something = vim_input('Say something in %s: ' % (G.AGENT.workspace,), '')
    if something:
        G.AGENT.send_msg(something)
