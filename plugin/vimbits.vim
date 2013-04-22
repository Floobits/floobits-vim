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
let g:floobits_plugin_dir = expand("<sfile>:p:h")

python << END_PYTHON
import os, sys
import vim
sys.path.append(vim.eval("g:floobits_plugin_dir"))

END_PYTHON

if filereadable(expand("<sfile>:p:h")."/floobits.py")
    pyfile <sfile>:p:h/floobits.py
else
    echohl WarningMsg |
    \ echomsg "Floobits plugin error: Can't find floobits.py in ".g:floobits_plugin_dir |
    \ echohl None
    finish
endif

function! s:MaybeChanged()
    if &modified
        python maybeBufferChanged()
    endif
endfunction

function! s:SetAutoCmd()
    let s:vim_events = ['InsertEnter', 'InsertChange', 'InsertLeave', 'QuickFixCmdPost', 'FileChangedShellPost', 'CursorMoved', 'CursorMovedI']
    let s:new_buf_events = ['BufWritePost', 'BufReadPost', 'BufEnter']
    augroup floobits
        " kill autocommands on reload
        autocmd!
        for cmd in s:vim_events
            exec 'autocmd '. cmd .' * call s:MaybeChanged()'
        endfor

        autocmd CursorHold * python CursorHold()
        autocmd CursorHoldI * python CursorHoldI()

        autocmd CursorMoved * python maybeSelectionChanged()
        autocmd CursorMovedI * python maybeSelectionChanged()

        for cmd in s:new_buf_events
            exec 'autocmd '. cmd .' * python maybeNewFile()'
        endfor

        " milliseconds
        exe 'setlocal updatetime=100'
    augroup END
endfunction

"TODO: populate with a default url of https://floobits.com/r/
command! -nargs=1 FlooJoinRoom :python joinroom(<f-args>)
command! FlooPartRoom :python partroom()
command! FlooToggleFollowMode :python follow()
command! FlooPing :python maybeSelectionChanged(True)
command! FlooDeleteBuf :python delete_buf()

call s:SetAutoCmd()
let g:floobits_plugin_loaded = 1
