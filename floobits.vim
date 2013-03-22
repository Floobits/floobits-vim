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

function! DispatchEvent()
    py handle_event('change!')
endfunction

function! s:SetAutoCmd()
    let s:vim_events = ['CursorMoved', 'CursorMovedI', 'InsertEnter', 'InsertChange', 'InsertLeave']
    augroup floobits
        " kill autocommands on reload
        autocmd!
        for cmd in s:vim_events
            exec 'autocmd '. cmd .' * call DispatchEvent()'
        endfor
    augroup END
endfunction

function! s:joinroom(url)
  py joinroom(url)
endfunction

call s:SetAutoCmd()
