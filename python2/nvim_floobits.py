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


class NvimFloobits(object):
    def __init__(self, vim):
        self.vim = vim
        #self.eventLoop = EventLoop(vim)
        #self.eventLoop.start()
        #command! -nargs=1 FlooJoinWorkspace :python floobits_check_and_join_workspace(<f-args>)
        vim.command('command! -nargs=1 FlooTest call rpcrequest(%d, "floo_test", <f-args>)' %
            self.vim.channel_id)

    def floo_test(self, test):
        self.vim.command('echom "floo_test" %s' % test)

    def on_tick(self):
        pass
