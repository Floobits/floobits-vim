" Copyright Floobits Inc 2013

if !has('python')
    echohl WarningMsg |
    \ echomsg "Sorry, the Floobits Vim plugin requires a Vim compiled with +python." |
    \ echohl None
    finish
endif

if exists("g:FloobitsPluginLoaded")
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
let g:FloobitsPluginDir = expand("<sfile>:p:h")

python << END_PYTHON
import os, sys
import vim
sys.path.append(vim.eval("g:FloobitsPluginDir"))

END_PYTHON

if filereadable(expand("<sfile>:p:h")."/floobits_wrapper.py")
    pyfile <sfile>:p:h/floobits_wrapper.py
else
    echohl WarningMsg |
    \ echomsg "Floobits plugin error: Can't find floobits.py in ".g:FloobitsPluginDir |
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

function! g:FloobitsGlobalTick()
    python global_tick()
endfunction

function! g:FloobitsGetSelection()
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

        autocmd CursorMoved * python maybe_selection_changed()
        autocmd CursorMovedI * python maybe_selection_changed()
        for cmd in s:new_buf_events
            exec 'autocmd '. cmd .' * python maybe_new_file()'
        endfor

        autocmd BufEnter * python buf_enter()
        autocmd BufWritePost * python on_save()
        " milliseconds
        if has('timers')
            call setinterval(100, 'python global_tick()')
        endif
        if has('async')
            call setinterval(100, 'python global_tick()')
        endif
    augroup END
endfunction

"TODO: populate with a default url of https://floobits.com/
command! -nargs=1 FlooJoinWorkspace :python check_and_join_workspace(<f-args>)

command! FlooLeaveWorkspace :python part_workspace()
command! FlooPartworkspace :python part_workspace()

command! FlooToggleFollowMode :python follow()

command! FlooSummon :python maybe_selection_changed(True)
command! FlooPing :python maybe_selection_changed(True)

command! FlooDeleteBuf :python delete_buf()

command! FlooOpenInBrowser :python open_in_browser()
command! FlooClearHighlights :python clear()
command! FlooToggleHighlights :python toggle_highlights()
command! FlooCompleteSignup :python complete_signup()
command! FlooUsersInWorkspace :python users_in_workspace()
command! FlooListMessages :python list_messages()
command! FlooSaySomething :python say_something()

command! -nargs=1 -complete=dir FlooShareDirPublic :python share_dir_public(<f-args>)
command! -nargs=1 -complete=dir FlooShareDirPrivate :python share_dir_private(<f-args>)
command! -nargs=? -complete=file FlooAddBuf :python add_buf(<f-args>)

command! FlooInfo :python info()

call s:SetAutoCmd()
let g:FloobitsPluginLoaded = 1
python check_credentials()
