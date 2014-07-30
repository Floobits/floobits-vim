import subprocess
import vim
import atexit

try:
    from . import msg, utils, reactor, shared as G, flooui
    from ..common import vim_handler, editor
except (ImportError, ValueError):
    from floo.common import msg, utils, reactor, shared as G, flooui
    from floo import vim_handler, editor


reactor = reactor.reactor
call_feedkeys = False
ticker = None
ticker_errors = 0
using_feedkeys = False


ticker_python = '''import sys; import subprocess; import time
args = ['{binary}', '--servername', '{servername}', '--remote-expr', 'g:FloobitsGlobalTick()']
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
'''

FLOOBITS_INFO = '''
floobits_version: {version}
# not updated until FlooJoinWorkspace is called
mode: {mode}
updatetime: {updatetime}
clientserver_support: {cs}
servername: {servername}
ticker_errors: {ticker_errors}
'''


def floobits_pause():
    global call_feedkeys, ticker

    if G.TIMERS:
        return

    if using_feedkeys:
        call_feedkeys = False
        vim.command('set updatetime=4000')
    else:
        if ticker is None:
            return
        try:
            ticker.kill()
        except Exception as e:
            print(e)
        ticker = None


def floobits_unpause():
    global call_feedkeys

    if G.TIMERS:
        return

    if using_feedkeys:
        call_feedkeys = True
        vim.command('set updatetime=250')
    else:
        start_event_loop()


def fallback_to_feedkeys(warning):
    global using_feedkeys
    using_feedkeys = True
    warning += ' Falling back to f//e hack which will break some key commands. You may need to call FlooPause/FlooUnPause before some commands.'
    msg.warn(warning)
    floobits_unpause()


def ticker_watcher(ticker):
    global ticker_errors
    if not G.AGENT:
        return
    ticker.poll()
    if ticker.returncode is None:
        return
    msg.warn('respawning new ticker')
    ticker_errors += 1
    if ticker_errors > 10:
        return fallback_to_feedkeys('Too much trouble with the floobits external ticker.')
    start_event_loop()
    utils.set_timeout(ticker_watcher, 2000, ticker)


def start_event_loop():
    global ticker

    if G.TIMERS:
        msg.debug('Your Vim was compiled with +timer support. Awesome!')
        return

    if not bool(int(vim.eval('has("clientserver")'))):
        return fallback_to_feedkeys('This VIM was not compiled with clientserver support. You should consider using a different vim!')

    exe = getattr(G, 'VIM_EXECUTABLE', None)
    if not exe:
        return fallback_to_feedkeys('Your vim was compiled with clientserver, but I don\'t know the name of the vim executable.'
                                    'Please define it in your ~/.floorc using the vim_executable directive. e.g. \'vim_executable mvim\'.')

    servername = vim.eval('v:servername')
    if not servername:
        return fallback_to_feedkeys('I can not identify the servername of this vim. You may need to pass --servername to vim at startup.')

    evaler = ticker_python.format(binary=exe, servername=servername, sleep='1.0')
    ticker = subprocess.Popen(['python', '-c', evaler],
                              stderr=subprocess.PIPE,
                              stdout=subprocess.PIPE)
    ticker.poll()
    utils.set_timeout(ticker_watcher, 500, ticker)


def floobits_stop_everything():
    if G.AGENT:
        reactor.stop()
        G.AGENT = None
    floobits_pause()
    # TODO: get this value from vim and reset it
    vim.command('set updatetime=4000')

# NOTE: not strictly necessary
atexit.register(floobits_stop_everything)


class VUI(flooui.FlooUI):
    def floobits_info(self):
        kwargs = {
            'cs': bool(int(vim.eval('has("clientserver")'))),
            'mode': (using_feedkeys and 'feedkeys') or 'client-server',
            'servername': vim.eval('v:servername'),
            'ticker_errors': ticker_errors,
            'updatetime': vim.eval('&l:updatetime'),
            'version': G.__PLUGIN_VERSION__,
        }

        msg.log(FLOOBITS_INFO.format(**kwargs))

    def vim_input(self, prompt, default, completion=None):
        vim.command('call inputsave()')
        if completion:
            cmd = "let user_input = input('%s', '%s', '%s')" % (prompt, default, completion)
        else:
            cmd = "let user_input = input('%s', '%s')" % (prompt, default)
        vim.command(cmd)
        vim.command('call inputrestore()')
        return vim.eval('user_input')

    def _make_agent(self, context, owner, workspace, auth, created_workspace):
        """@returns new Agent()"""
        floobits_stop_everything()
        if not G.TIMERS:
            start_event_loop()
        return vim_handler.VimHandler(owner, workspace, auth, created_workspace)

    def user_y_or_n(self, context, prompt, affirmation_txt, cb):
        """@returns True/False"""
        return cb(editor.ok_cancel_dialog(prompt))

    def user_dir(self, context, prompt, default, cb):
        return cb(self.vim_input(prompt, default, "dir"))

    def user_select(self, context, prompt, choices_big, choices_small, cb):
        """@returns (choice, index)"""
        # default = choices_big.index(default) + 1
        choices_str = '\n'.join(['&%s' % choice for choice in choices_big])
        try:
            choice = int(vim.eval('confirm("%s", "%s", %s)' % (prompt, choices_str, 1)))
        except KeyboardInterrupt:
            return cb(None, -1)
        if choice == 0:
            return cb(None, -1)
        return cb(choices_big[choice - 1], choice - 1)

    def user_charfield(self, context, prompt, initial, cb):
        """@returns String"""
        return cb(self.vim_input(prompt, initial))

    def get_a_window(self, abs_path, cb):
        """opens a project in a window or something"""
        return cb()

    def floobits_part_workspace(self):
        if not G.AGENT:
            return msg.warn('Unable to leave workspace: You are not joined to a workspace.')
        floobits_stop_everything()
        msg.log('You left the workspace.')

    def floobits_users_in_workspace(self):
        if not G.AGENT:
            return msg.warn('Not connected to a workspace.')
        vim.command('echom "Users connected to %s"' % (G.AGENT.workspace,))
        for user in G.AGENT.workspace_info['users'].values():
            vim.command('echom "  %s connected with %s on %s"' % (user['username'], user['client'], user['platform']))

    def floobits_list_messages(self):
        if not G.AGENT:
            return msg.warn('Not connected to a workspace.')
        vim.command('echom "Recent messages for %s"' % (G.AGENT.workspace,))
        for message in G.AGENT.get_messages():
            vim.command('echom "  %s"' % (message,))

    def floobits_say_something(self):
        if not G.AGENT:
            return msg.warn('Not connected to a workspace.')
        something = self.vim_input('Say something in %s: ' % (G.AGENT.workspace,), '')
        if something:
            G.AGENT.send_msg(something)
