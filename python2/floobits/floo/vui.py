import subprocess
import atexit

try:
    from . import msg, utils, reactor, shared as G, flooui
    from ..common import vim_handler, editor
except (ImportError, ValueError):
    from floo.common import msg, utils, reactor, shared as G, flooui
    from floo import vim_handler, editor


reactor = reactor.reactor


FLOOBITS_INFO = '''
floobits_version: {version}
# not updated until FlooJoinWorkspace is called
updatetime: {updatetime}
clientserver_support: {cs}
servername: {servername}
'''

vim = None


def stop_everything():
    if G.AGENT:
        reactor.stop()
        G.AGENT = None


class VUI(flooui.FlooUI):
    def info(self):
        kwargs = {
            'cs': bool(int(vim.eval('has("clientserver")'))),
            'servername': vim.eval('v:servername'),
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
        stop_everything()
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

    def part_workspace(self):
        if not G.AGENT:
            return msg.warn('Unable to leave workspace: You are not joined to a workspace.')
        stop_everything()
        msg.log('You left the workspace.')

    def users_in_workspace(self):
        if not G.AGENT:
            return msg.warn('Not connected to a workspace.')
        vim.command('echom "Users connected to %s"' % (G.AGENT.workspace,))
        for user in G.AGENT.workspace_info['users'].values():
            vim.command('echom "  %s connected with %s on %s"' % (user['username'], user['client'], user['platform']))

    def list_messages(self):
        if not G.AGENT:
            return msg.warn('Not connected to a workspace.')
        vim.command('echom "Recent messages for %s"' % (G.AGENT.workspace,))
        for message in G.AGENT.get_messages():
            vim.command('echom "  %s"' % (message,))

    def say_something(self):
        if not G.AGENT:
            return msg.warn('Not connected to a workspace.')
        something = self.vim_input('Say something in %s: ' % (G.AGENT.workspace,), '')
        if something:
            G.AGENT.send_msg(something)
