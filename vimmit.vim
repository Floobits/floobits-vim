if !has('python')
    echo "no python"
    finish
endif

pyfile ./floobits.py

py test_test_test()

function! DispatchEvent()
    py handle_shit('shit moved')
endfunction

augroup floobits
    " Eventually we also want InsertEnter, InsertChange, InsertLeave, and CursorMovedI
    autocmd!
    autocmd CursorMoved,CursorMovedI * call DispatchEvent()
augroup END

function! Capitalsdf()
python << END_PYTHON

import vim
import urllib2

import json

# we define a timeout that we'll use in the API call. We don't want
# users to wait much.
TIMEOUT = 20
URL = "http://reddit.com/.json"

try:
    # Get the posts and parse the json response
    response = urllib2.urlopen(URL, None, TIMEOUT).read()
    json_response = json.loads(response)

    posts = json_response.get("data", "").get("children", "")

    # vim.current.buffer is the current buffer. It's list-like object.
    # each line is an item in the list. We can loop through them delete
    # them, alter them etc.
    # Here we delete all lines in the current buffer
    del vim.current.buffer[:]

    # Here we append some lines above. Aesthetics.
    vim.current.buffer[0] = 80 * "-"

    for post in posts:
        # In the next few lines, we get the post details
        post_data = post.get("data", {})
        up = post_data.get("ups", 0)
        down = post_data.get("downs", 0)
        title = post_data.get("title", "NO TITLE").encode("utf-8")
        score = post_data.get("score", 0)
        permalink = post_data.get("permalink").encode("utf-8")
        url = post_data.get("url").encode("utf-8")
        comments = post_data.get("num_comments")

        # And here we append line by line to the buffer.
        # First the upvotes
        vim.current.buffer.append("↑ %s" % up)
        # Then the title and the url
        vim.current.buffer.append("    %s [%s]" % (title, url,))
        # Then the downvotes and number of comments
        vim.current.buffer.append("↓ %s    | comments: %s [%s]" % (down, comments, permalink,))
        # And last we append some "-" for visual appeal.
        vim.current.buffer.append(80 * "-")

except Exception, e:
    print e

END_PYTHON
" Here the python code is closed. We can continue writing VimL or python again.
endfunction

