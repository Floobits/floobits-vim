" Copyright Floobits LLC 2013

if !has('python')
    echohl WarningMsg |
    \ echomsg "Sorry, the Floobits Vim plugin requires a Vim compiled with +python." |
    \ echohl None
    finish
endif

if exists("g:floobits_plugin_loaded")
    finish
endif

" p flag expands the absolute path. Sorry for the global
let g:floobits_vim_file = expand("<sfile>:p")

python << END_PYTHON
import os, sys
import vim
sys.path.append(os.path.dirname(vim.eval("g:floobits_vim_file")))

END_PYTHON

let s:floobits_plugin_dir = expand("<sfile>:p:h")
if filereadable(expand("<sfile>:p:h")."/floobits.py")
    pyfile <sfile>:p:h/floobits.py
else
    echohl WarningMsg |
    \ echomsg "Floobits plugin error: Can't find floobits.py in ".s:floobits_plugin_dir |
    \ echohl None
    finish
endif

if !exists("g:floobits_update_interval")
    " milliseconds
    let g:floobits_update_interval = 20
endif

function! s:SetAutoCmd()
    let s:vim_events = ['InsertEnter', 'InsertChange', 'InsertLeave', 'QuickFixCmdPost']
    augroup floobits
        " kill autocommands on reload
        autocmd!
        for cmd in s:vim_events
            exec 'autocmd '. cmd .' * python maybeBufferChanged()'
        endfor
        autocmd CursorHold * python CursorHold()
        autocmd CursorHoldI * python CursorHoldI()
        " BufFilePost
        exe 'set updatetime='.g:floobits_update_interval
    augroup END
endfunction

"TODO: populate with a default url of https://floobits.com/r/
command! -nargs=1 FlooJoinRoom :python joinroom(<f-args>)

call s:SetAutoCmd()

let g:floobits_plugin_loaded = 1
