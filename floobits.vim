if !has('python')
    echo "Sorry, this plugin requires a vim compiled with +python."
    finish
endif

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

autocmd VimEnter * call s:SetAutoCmd()
