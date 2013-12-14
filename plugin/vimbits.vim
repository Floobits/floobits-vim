" Copyright Floobits Inc 2013

if !has('python')
    echohl WarningMsg |
    \ echomsg "Sorry, the Floobits Vim plugin requires a Vim compiled with +python." |
    \ echohl None
    finish
endif

if exists("g:floobits_plugin_loaded")
    finish
endif

if !exists("floo_log_level")
    let floo_log_level = "msg"
endif
if !exists("floo_delete_local_files")
    let floo_delete_local_files = 1
endif
if !exists("floo_show_highlights")
    let floo_show_highlights = 1
endif
if !exists("floo_sparse_mode")
    let floo_sparse_mode = 0
endif

" p flag expands the absolute path. Sorry for the global
let g:floobits_plugin_dir = expand("<sfile>:p:h")

python << END_PYTHON
import os, sys
import vim
sys.path.append(vim.eval("g:floobits_plugin_dir"))

END_PYTHON

if filereadable(expand("<sfile>:p:h")."/floobits_wrapper.py")
    pyfile <sfile>:p:h/floobits_wrapper.py
else
    echohl WarningMsg |
    \ echomsg "Floobits plugin error: Can't find floobits.py in ".g:floobits_plugin_dir |
    \ echohl None
    finish
endif

function! s:MaybeChanged()
    python floobits_maybe_buffer_changed()
endfunction

function! g:FlooSetReadOnly()
    " this doesn't work for the first time from dired ?!?
    setlocal nomodifiable
endfunction

function! g:floobits_global_tick()
    python floobits_global_tick()
endfunction

function! g:floobits_get_selection()
    let m = tolower(mode())
    try
        if 'v' == m
            let pos = getpos("v")
            let line = pos[1]
            let col = pos[2]
            let start = line2byte(line) + col - 2
            let pos = getpos(".")
            let line = pos[1]
            let col = pos[2]
            let end = line2byte(line) + col - 2
            return [[start, end]]
        else
            let pos = line2byte(line(".")) + col(".") - 2
            return [[pos, pos]]
        endif
    catch a:exception
        return [[0, 0]]
    endtry
endfunction

function! s:SetAutoCmd()
    let s:vim_events = ['InsertEnter', 'InsertChange', 'InsertLeave', 'QuickFixCmdPost', 'FileChangedShellPost', 'CursorMoved', 'CursorMovedI']
    let s:new_buf_events = ['BufWritePost', 'BufReadPost', 'BufWinEnter']
    augroup floobits
        " kill autocommands on reload
        autocmd!
        for cmd in s:vim_events
            exec 'autocmd '. cmd .' * call s:MaybeChanged()'
        endfor

        autocmd CursorHold * python floobits_cursor_hold()
        autocmd CursorHoldI * python floobits_cursor_holdi()
        autocmd CursorMoved * python floobits_maybe_selection_changed()
        autocmd CursorMovedI * python floobits_maybe_selection_changed()
        for cmd in s:new_buf_events
            exec 'autocmd '. cmd .' * python floobits_maybe_new_file()'
        endfor

        autocmd BufEnter * python floobits_buf_enter()
        autocmd BufWritePost * python floobits_on_save()
        " milliseconds
        if has('timers')
            call setinterval(100, 'python floobits_global_tick()')
        endif
        if has('async')
            call setinterval(100, 'python floobits_global_tick()')
        endif
    augroup END
endfunction

"TODO: populate with a default url of https://floobits.com/
command! -nargs=1 FlooJoinWorkspace :python floobits_join_workspace(<f-args>)

command! FlooLeaveWorkspace :python floobits_part_workspace()
command! FlooPartworkspace :python floobits_part_workspace()

command! FlooToggleFollowMode :python floobits_follow()

command! FlooSummon :python floobits_maybe_selection_changed(True)
command! FlooPing :python floobits_maybe_selection_changed(True)

command! FlooDeleteBuf :python floobits_delete_buf()

command! FlooPause :python floobits_pause()
command! FlooUnPause :python floobits_unpause()
command! FlooOpenInBrowser :python floobits_open_in_browser()
command! FlooClearHighlights :python floobits_clear()
command! FlooToggleHighlights :python floobits_toggle_highlights()
command! FlooCompleteSignup :python floobits_complete_signup()

command! -nargs=1 -complete=dir FlooShareDir :python floobits_share_dir(<f-args>)
command! -nargs=1 -complete=dir FlooShareDirPrivate :python floobits_share_dir_private(<f-args>)
command! -nargs=? -complete=file FlooAddBuf :python floobits_add_buf(<f-args>)

command! FlooInfo :python floobits_info()

python floobits_check_credentials()
call s:SetAutoCmd()
let g:floobits_plugin_loaded = 1
