import vim

from common import msg, utils


# Foreground: background
COLORS = (
    ('white', 'red'),
    ('black', 'yellow'),
    ('black', 'green'),
    ('white', 'blue'),
)
HL_RULES = ['ctermfg=%s ctermbg=%s guifg=%s guibg=%s' % (fg, bg, fg, bg) for fg, bg in COLORS]


def user_id_to_region(user_id):
    return "floobitsuser%s" % user_id


class View(object):
    """editors representation of the buffer"""

    def __init__(self, vim_buf, buf):
        self.vim_buf = vim_buf
        self.buf = buf

    def __repr__(self):
        return '%s %s %s' % (self.native_id, self.buf['id'], self.buf['path'].encode('utf-8'))

    # def __str__(self):
    #     return repr(self)
    __str__ = __repr__

    def _offset_to_vim(self, offset):
        current_offset = 0
        for line_num, line in enumerate(self.vim_buf):
            next_offset = len(line) + 1
            if current_offset + next_offset > offset:
                break
            current_offset += next_offset
        col = offset - current_offset
        msg.debug('offset %s is line %s column %s' % (offset, line_num + 1, col + 1))
        return line_num + 1, col + 1

    @property
    def native_id(self):
        return self.vim_buf.number

    def is_loading(self):
        return False

    def get_text(self):
        text = '\n'.join(self.vim_buf[:])
        return text.decode('utf-8')

    def set_text(self, text):
        msg.debug('\n\nabout to patch %s %s' % (str(self), self.vim_buf.name))
        try:
            msg.debug("now buf is loadedish? %s" % vim.eval('bufloaded(%s)' % self.native_id))
            self.vim_buf[:] = text.encode('utf-8').split('\n')
        except Exception as e:
            msg.error("couldn't apply patches because: %s!\nThe unencoded text was: %s" % (str(e), text))
            raise

    def apply_patches(self, buf, patches, username):
        cursor_offset = self.get_cursor_offset()
        msg.debug('cursor offset is %s bytes' % cursor_offset)
        self.set_text(patches[0])

        for patch in patches[2]:
            offset = patch[0]
            length = patch[1]
            patch_text = patch[2]
            if cursor_offset > offset:
                new_offset = len(patch_text) - length
                cursor_offset += new_offset

        self.set_cursor_position(cursor_offset)

    def focus(self):
        vim.command(':silent! edit! %s | :silent! :filetype detect' % self.vim_buf.name)

    def set_cursor_position(self, offset):
        line_num, col = self._offset_to_vim(offset)
        command = ':silent! call setpos(".", [%s, %s, %s, %s])' % (self.native_id, line_num, col, 0)
        msg.debug('setting pos: %s' % command)
        vim.command(command)

    def get_cursor_position(self):
        """ [bufnum, lnum, col, off] """
        return vim.eval('getpos(".")')

    def get_cursor_offset(self):
        return int(vim.eval('line2byte(line("."))+col(".")')) - 2

    def get_selections(self):
        cursor = self.get_cursor_offset()
        return [[cursor, cursor]]

    def clear_highlight(self, user_id):
        region = user_id_to_region(user_id)
        msg.debug('clearing selections for user %s in view %s' % (user_id, self.vim_buf.name))
        vim.command(':silent highlight clear %s | :silent! syntax clear %s' % (region, region))

    def highlight(self, ranges, user_id):
        msg.debug('highlighting ranges %s' % (ranges))
        if vim.current.buffer.number != self.vim_buf.number:
            return
        region = user_id_to_region(user_id)

        hl_rule = HL_RULES[user_id % len(HL_RULES)]
        vim.command(":silent highlight %s %s" % (region, hl_rule))

        for _range in ranges:
            start_row, start_col = self._offset_to_vim(_range[0])
            end_row, end_col = self._offset_to_vim(_range[1])
            if start_row == end_row and start_col == end_col:
                if end_col >= len(self.vim_buf[end_row - 1]):
                    end_row += 1
                    end_col = 1
                else:
                    end_col += 1
            vim_region = ":syntax region {region} start=/\%{start_col}v\%{start_row}l/ end=/\%{end_col}v\%{end_row}l/".\
                format(region=region, start_col=start_col, start_row=start_row, end_col=end_col, end_row=end_row)
            vim.command(vim_region)

    def rename(self, name):
        msg.debug('renaming %s to %s' % (self.vim_buf.name, name))
        current = vim.current.buffer
        text = self.get_text()
        old_name = self.vim_buf.name
        old_number = self.native_id
        with open(name, 'wb') as fd:
            fd.write(text.encode('utf-8'))
        vim.command('edit! %s' % name)
        self.vim_buf = vim.current.buffer
        vim.command('edit! %s' % current.name)
        vim.command('bdelete! %s' % old_number)
        try:
            utils.rm(old_name)
        except Exception as e:
            msg.debug("couldn't delete %s... maybe thats OK?" % str(e))

    def save(self):
        vim.command(':s!')
