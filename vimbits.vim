if !has('python')
    echo "Sorry, this plugin requires a vim compiled with +python."
    finish
endif

let g:floobits_vim_file = expand("<sfile>")

python << END_PYTHON
import os, sys
import vim
sys.path.append(os.path.dirname(vim.eval("g:floobits_vim_file")))

END_PYTHON

pyfile ./floobits.py

if !exists("g:floobits_update_interval")
    let g:floobits_update_interval = 100
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
