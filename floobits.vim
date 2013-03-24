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


autocmd asdf * py asdf()

autocmd CursorMoved * doau asdf
py asdf()

function! DispatchEvent()
    py handle_event()
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

function! Floojoinroom()
  py joinroom("https://floobits.com:3448/r/kansface/holy-shit-its-vim/")
endfunction

" call s:SetAutoCmd()
