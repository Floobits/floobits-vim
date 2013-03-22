if !has('python')
    echo "no python"
    finish
endif

pyfile ./floobits.py

function! DispatchEvent()
    py handle_shit('shit moved')
endfunction

augroup floobits
    " Eventually we also want InsertEnter, InsertChange, InsertLeave, and CursorMovedI
    autocmd!
    autocmd CursorMoved,CursorMovedI * call DispatchEvent()
augroup END

function! joinroom(url)
  py joinroom(url)
endfunction

