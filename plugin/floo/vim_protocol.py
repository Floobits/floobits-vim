"""Vim specific logic"""
import os
import time

import vim

from common import msg, shared as G, utils
import protocol

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

    def __str__(self):
        return repr(self)

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

    def apply_patches(self, buf, patches):
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
        command = ':silent! setpos(".", [%s, %s, %s, %s])' % (self.native_id, line_num, col, 0)
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
        return
        region = user_id_to_region(user_id)
        msg.debug('clearing selections for user %s in view %s' % (user_id, self.vim_buf.name))
        vim.command(':silent highlight clear %s | :silent! syntax clear %s' % (region, region))

    def highlight(self, ranges, user_id):
        return
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


class Protocol(protocol.BaseProtocol):
    """understands vim"""
    CLIENT = 'VIM'

    def on_room_info(self, workspace_info):
        super(Protocol, self).on_room_info(workspace_info)
        vim.command(':Explore %s | redraw' % G.PROJECT_PATH)

    def maybe_selection_changed(self, vim_buf, is_ping):
        buf = self.get_buf(vim_buf)
        if not buf:
            msg.debug('no buffer found for view %s' % vim_buf.number)
            return
        view = self.get_view(buf['id'])
        msg.debug("selection changed: %s %s %s" % (vim_buf.number, buf['id'], view))
        self.SELECTION_CHANGED.append([view, is_ping])

    def maybe_buffer_changed(self, vim_buf):
        text = vim_buf[:]
        buf = self.get_buf(vim_buf)
        if not buf or 'buf' not in buf:
            return
        if buf['buf'] != text:
            self.BUFS_CHANGED.append(buf['id'])

    def get_vim_buf_by_path(self, p):
        for vim_buf in vim.buffers:
            if vim_buf.name and p == utils.to_rel_path(vim_buf.name):
                return vim_buf
        return None

    def get_view(self, buf_id):
        buf = self.FLOO_BUFS.get(buf_id)
        if not buf:
            return None

        vb = self.get_vim_buf_by_path(buf['path'])
        if not vb:
            return None

        if vim.eval('bufloaded(%s)' % vb.number) == '0':
            return None

        return View(vb, buf)

    def create_view(self, buf):
        path = self.save_buf(buf)
        vb = self.get_vim_buf_by_path(buf['path'])
        if vb:
            return View(vb, buf)

        vim.command(':edit! %s' % path)
        vb = self.get_vim_buf_by_path(buf['path'])
        if vb is None:
            msg.debug('vim buffer is none even though we tried to open it: %s' % path)
            return
        return View(vb, buf)

    def get_buf(self, vim_buf):
        """None- no sharing, False- should be but isn't """
        if vim_buf.name is None or vim_buf.name == "":
            msg.debug('get:buf buffer has no filename')
            return None

        if not utils.is_shared(vim_buf.name):
            msg.debug('get_buf: %s is not shared' % vim_buf.name)
            return None

        buf = self.get_buf_by_path(vim_buf.name)
        if buf:
            return buf

        msg.debug('get_buf: no buf has path %s' % vim_buf.name)
        return False

    def save_buf(self, buf):
        path = utils.get_full_path(buf['path'])
        utils.mkdir(os.path.split(path)[0])
        with open(path, 'wb') as fd:
            if buf['encoding'] == 'utf8':
                fd.write(buf['buf'].encode('utf-8'))
            else:
                fd.write(buf['buf'])
        return path

    def chat(self, username, timestamp, message, self_msg=False):
        pass
        # envelope = msg.MSG(message, timestamp, username)
        # if not self_msg:
        #     self.chat_deck.appendleft(envelope)
        # envelope.display()

    def on_msg(self, data):
        timestamp = data.get('time') or time.time()
        msg.log('[%s] <%s> %s' % (time.ctime(timestamp), data.get('username', ''), data.get('data', '')))

    def update_view(self, buf, view=None):
        msg.debug('updating view for buf %s' % buf['id'])
        view = view or self.get_view(buf['id'])
        if not view:
            msg.log('view for buf %s not found. not updating' % buf['id'])
            return
        self.MODIFIED_EVENTS.put(1)
        view.set_text(buf['buf'])

    def on_part(self, data):
        msg.log('%s left the workspace' % data['username'])
        user_id = data['user_id']
        highlight = self.user_highlights.get(user_id)
        if not highlight:
            return
        view = self.get_view(highlight['id'])
        if not view:
            return
        if vim.current.buffer.number != view.native_id:
            return
        view.clear_highlight(user_id)
        del self.user_highlights[user_id]

    def clear_highlight(self, path):
        """it is assumed path is the path of the current buffer"""
        if not path:
            return

        if not utils.is_shared(path):
            return

        for user_id, highlight in self.user_highlights.items():
            full_path = utils.get_full_path(highlight['path'])
            if path == full_path:
                region = user_id_to_region(user_id)
                vim.command(":highlight clear %s" % region)
