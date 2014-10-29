from threading import Thread
from time import sleep, strftime
from floobits import floobits
from floobits.floo import vui, editor


class EventLoop(Thread):
    def __init__(self, vim):
        super(EventLoop, self).__init__()
        self.vim = vim
        self.intervals = []

    def run(self):
        while True:
            sleep(0.1)
            self.vim.session.post('tick')


commands = [
    {'name': 'FlooJoinWorkspace', 'func': 'check_and_join_workspace', 'arg': '1'},
    {'name': 'FlooShareDirPublic', 'func': 'share_dir_public', 'arg': '1', 'complete': 'dir'},
    {'name': 'FlooShareDirPrivate', 'func': 'share_dir_private', 'arg': '1', 'complete': 'dir'},
    {'name': 'FlooAddBuf', 'func': 'add_buf', 'arg': '1', 'complete': 'file'},
    {'name': 'FlooLeaveWorkspace', 'func': 'part_workspace'},
    {'name': 'FlooToggleFollowMode', 'func': 'follow'},
    {'name': 'FlooSummon', 'func': 'maybe_selection_changed'},
    {'name': 'FlooDeleteBuf','func': 'delete_buf'},
    {'name': 'FlooOpenInBrowser','func': 'open_in_browser'},
    {'name': 'FlooClearHighlights','func': 'clear'},
    {'name': 'FlooToggleHighlights','func': 'toggle_highlights'},
    {'name': 'FlooCompleteSignup','func': 'complete_signup'},
    {'name': 'FlooUsersInWorkspace','func': 'users_in_workspace'},
    {'name': 'FlooListMessages','func': 'list_messages'},
    {'name': 'FlooSaySomething','func': 'say_something'},
    {'name': 'FlooInfo','func': 'info'},
]
event_handlers = [
    'maybe_selection_changed',
    'maybe_buffer_changed',
    'maybe_new_file',
    'buf_enter',
    'on_save',
]
buffer_events = [
    'InsertEnter',
    'InsertChange',
    'InsertLeave',
    'QuickFixCmdPost',
    'FileChangedShellPost',
    'CursorMoved',
    'CursorMovedI',
]

file_events = ['BufWritePost', 'BufReadPost', 'BufWinEnter']


class NvimFloobits(object):
    def __init__(self, vim):
        self.vim = vim
        floobits.vim = vim
        vui.vim = vim
        editor.vim = vim
        # kill autocommands on reload
        vim.command('!autocmd')
        for command in commands:
            self.add_command(command['name'], command['func'], command.get('arg', None),
                         command.get('complete', None)
        for event in buffer_events:
            self.add_autocmd(event, "maybe_buffer_changed")
        self.add_autocmd("CursorMoved", "maybe_selection_changed")
        self.add_autocmd("CursorMovedI", "maybe_selection_changed")
        for event in file_events:
            self.add_autocmd(event, "maybe_new_file")
        self.add_autocmd("BufEnter", "buf_enter")
        self.add_autocmd("BufWritePost", "on_save")
        #self.eventLoop = EventLoop(vim)
        #self.eventLoop.start()
        floobits.check_credentials()

    def on_tick(self):
        floobits.global_tick()

    def add_autocmd(self, event, handler):
        vim.command('autocmd  %s * rpcrequest(%d, "%s")' % (event, self.vim.channel_id, handler))

    def add_command(self, commandName, commandHandler, numArgs=None, complete=None):
        args = ""
        fargs = ""
        if numArgs is not None:
            args += "-nargs=%s " % numArgs
            fargs = ", <f-args>"
        if complete is not None:
            args += "-complete=%s " % complete

        vim.command('command! %s %s rpcrequest(%d, "%s"%s)' % (
                    args, commandName, self.vim.channel_id, commandHandler, fargs)


def add_command(funcName, hasArg=None):
    if not hasArg:
        def func(self):
           vim.command('echom "called %s"' % funcName)
           #getattr(floobits, funcName)()
    else:
        def func(self, arg):
           getattr(floobits, funcName)(arg)

    func.__name__ = funcName
    setattr(NvimFloobits, func.__name__, func)

for command in commands:
    add_command(command['func'], command.get('arg', None))

for handler in event_handlers:
    add_command(handler)
