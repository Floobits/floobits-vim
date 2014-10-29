from threading import Thread
from time import sleep, strftime


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
    {'name': 'FlooShareDirPublic', 'func': 'share_dir_public', 'arg': '1', 'complete': 'dir'}
    {'name': 'FlooShareDirPrivate', 'func': 'share_dir_private', 'arg': '1', 'complete': 'dir'}
    {'name': 'FlooAddBuf', 'func': 'add_buf', 'arg': '1', 'complete': 'file'}
    {'name': 'FlooLeaveWorkspace', 'func': 'part_workspace',},
    {'name': 'FlooToggleFollowMode', 'func': 'follow',},
    {'name': 'FlooSummon', 'func': 'maybe_selection_changed',},
    {'name': 'FlooDeleteBuf','func': 'delete_buf',},
    {'name': 'FlooOpenInBrowser','func': 'open_in_browser',},
    {'name': 'FlooClearHighlights','func': 'clear',},
    {'name': 'FlooToggleHighlights','func': 'toggle_highlights',},
    {'name': 'FlooCompleteSignup','func': 'complete_signup',},
    {'name': 'FlooUsersInWorkspace','func': 'users_in_workspace',},
    {'name': 'FlooListMessages','func': 'list_messages',},
    {'name': 'FlooSaySomething','func': 'say_something',},
    {'name': 'FlooInfo','func': 'info',},
]
eventHandlers = [
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

file_events = ['BufWritePost', 'BufReadPost', 'BufWinEnter',]

#floobits_maybe_buffer_changed

class NvimFloobits(object):
    def __init__(self, vim):
        self.vim = vim
        # kill autocommands on reload
        vim.command('!autocmd')
        for command in commands:
            self.command(command['name'], command['func'], command.get('arg', None),
                         command.get('complete', None)
        for event in buffer_events:
            vim.command('autocmd  %s * rpcrequest(%d, "maybe_buffer_changed")' % (
                event, self.vim.channel_id))
        vim.command('autocmd  CursorMoved * rpcrequest(%d, "maybe_selection_changed")' % (
            self.vim.channel_id))
        vim.command('autocmd  CursorMovedI * rpcrequest(%d, "maybe_selection_changed")' % (
            self.vim.channel_id))
        for event in file_events:
            vim.command('autocmd  %s * rpcrequest(%d, "maybe_new_file")' % (
                event, self.vim.channel_id))
        vim.command('autocmd  BufEnter * rpcrequest(%d, "buf_enter")' % (
            self.vim.channel_id))
        vim.command('autocmd  BufWritePost * rpcrequest(%d, "on_save")' % (
            self.vim.channel_id))
        #self.eventLoop = EventLoop(vim)
        #self.eventLoop.start()
        floobits.check_credentials()


    def on_tick(self):
        pass

    def command(self, commandName, commandHandler, numArgs=None, complete=None):
        if not numArgs
            vim.command('command! %s rpcrequest(%d, "%s")' % (
                commandName, self.vim.channel_id, commandHandler)
        else:
            if complete:
                vim.command('command! -nargs=%s -complete=%s %s rpcrequest(%d, "%s", <f-args>)' % (
                    numArgs, complete, commandName, self.vim.channel_id, commandHandler)
            else:
                vim.command('command! -nargs=%s %s rpcrequest(%d, "%s", <f-args>)' % (
                    numArgs, commandName, self.vim.channel_id, commandHandler)


def add_command(funcName, hasArg=None):
    if not hasArg:
        def func(self):
           getattr(floobits, funcName)()
    else:
        def func(self, arg):
           getattr(floobits, funcName)(arg)

    func.__name__ = funcName
    setattr(NvimFloobits, func.__name__, func)

for command in commands:
    add_command(command['func'], command.get('arg', None))
