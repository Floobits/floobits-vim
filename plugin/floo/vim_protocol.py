"""Vim specific logic"""
import os

import vim

import msg
import shared as G
import utils
import protocol


class View(object):
    """editors representation of the buffer"""

    def __init__(self, vim_buf, buf):
        self.vim_buf = vim_buf
        self.buf = buf

    @property
    def native_id(self):
        msg.debug(dir(self.vim_buf))
        return self.vim_buf.number

    def is_loading(self):
        return False

    def get_text(self):
        text = '\n'.join(self.vim_buf)
        msg.debug('get_text: %s' % text)
        return text

    def set_text(self, text):
        msg.debug('setting text to %s' % text.encode('utf-8').split('\n'))
        self.vim_buf[:] = text.encode('utf-8').split('\n')

    def apply_patches(self, buf, patches):
        cursor_offset = self.get_selections()

        self.set_text(patches[0])

        for patch in patches[2]:
            offset = patch[0]
            length = patch[1]
            patch_text = patch[2]
            self.MODIFIED_EVENTS.put(1)
            new_offset = len(patch_text) - length
            if cursor_offset > offset:
                cursor_offset += new_offset

        cursor_offset += 2
        current_offset = 0
        for line_num, line in enumerate(self.vim_buf):
            current_offset += len(line)
            if current_offset > cursor_offset:
                cursor_offset -= len(line)
                break
        col = current_offset - cursor_offset
        vim.eval('setpos(".", [%s, %s, %s, %s])' % (self.vim_buf.number, line_num, col, 0))

    def get_cursor_position(self):
        """ [bufnum, lnum, col, off] """
        return vim.eval('getpos(".")')

    def get_cursor_offset():
        vim.eval('line2byte(line("."))-2+col(".")')

    def get_selections(self):
        return []

    def clear_selections(self):
        msg.debug('clearing selections for view %s' % self.vim_buf.name)
        pass

    def highlight(self, ranges, user_id):
        msg.debug('highlighting ranges %s' % (ranges))
        # regions = []
        # for r in ranges:
        #     regions.append(sublime.Region(*r))
        # region_key = 'floobits-highlight-%s' % (data['user_id'])
        # view.erase_regions(region_key)
        # view.add_regions(region_key, regions, region_key, 'dot', sublime.DRAW_OUTLINED)
        # if ping:
        #     G.ROOM_WINDOW.focus_view(view)
        #     view.show_at_center(regions[0])
        pass

    def rename(self, name):
        msg.debug('renaming %s to %s' % (self.vim_buf.name, name))
        pass


class Protocol(protocol.BaseProtocol):
    """understands vim"""
    CLIENT = 'VIM'

    def on_room_info(self, room_info):
        super(Protocol, self).on_room_info(room_info)
        vim.command(':Explore %s' % G.PROJECT_PATH)

    def maybe_changed(self, buf_num):
        buf = vim.current.buffer
        buf_num = vim.eval("bufnr('%')")
        text = buf[:]
        buf = self.get_buf(int(buf_num))
        if buf is None:
            msg.debug('no buffer found for view %s' % buf_num)
            msg.debug('buffers:')
            for buf_id, buf in self.FLOO_BUFS.iteritems():
                msg.debug('id %s buf %s' % (buf_id, buf['path']))
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
        if vb:
            return View(vb, buf)
        return None

    def create_view(self, buf):
        path = self.save_buf(buf)
        vb = self.get_vim_buf_by_path(buf['path'])
        if vb:
            return View(vb, buf)

        vim.command(':Explore %s' % path)
        vb = self.get_vim_buf_by_path(buf['path'])
        return View(vb, buf)

    def get_buf(self, buf_num):
        vim_buf = None
        for vb in vim.buffers:
            if vb.number == buf_num:
                vim_buf = vb
                break
        if vim_buf is None:
            msg.debug('get_buf: vim.buffers[%s] does not exist' % buf_num)
            return None
        if vim_buf.name is None:
            msg.debug('get:buf buffer has no filename')
            return None
        if not utils.is_shared(vim_buf.name):
            msg.debug('get_buf: %s is not shared' % vim_buf.name)
            return None
        # TODO: this is inefficient as hell
        for buf_id, buf in self.FLOO_BUFS.iteritems():
            if self.get_vim_buf_by_path(buf['path']):
                return buf
        msg.debug('get_buf: no buf has path %s' % buf_num)
        return None

    def save_buf(self, buf):
        path = utils.get_full_path(buf['path'])
        utils.mkdir(os.path.split(path)[0])
        with open(path, 'wb') as fd:
            fd.write(buf['buf'].encode('utf-8'))
        return path

    def delete_buf(self, buf_id):
        # TODO: somehow tell the user about this. maybe delete on disk too?
        del G.FLOO_BUFS[buf_id]

    def chat(self, username, timestamp, message, self_msg=False):
        raise NotImplemented()
        # envelope = msg.MSG(message, timestamp, username)
        # if not self_msg:
        #     self.chat_deck.appendleft(envelope)
        # envelope.display()

    def update_view(self, buf, view=None):
        msg.debug('updating view for buf %s' % buf['id'])
        view = view or self.get_view(buf['id'])
        if not view:
            msg.log('view for buf %s not found. not updating' % buf['id'])
            return

        # visible_region = view.visible_region()
        # viewport_position = view.viewport_position()
        # region = sublime.Region(0, view.size())
        # # deep copy
        # selections = [x for x in view.sel()]
        self.MODIFIED_EVENTS.put(1)
        view.set_text(buf['buf'])
        # try:
        #     edit = view.begin_edit()
        #     view.replace(edit, region, buf['buf'])
        # except Exception as e:
        #     msg.error('Exception updating view: %s' % e)
        # finally:
        #     view.end_edit(edit)
        # sublime.set_timeout(lambda: view.set_viewport_position(viewport_position, False), 0)
        # view.sel().clear()
        # view.show(visible_region, False)
        # for sel in selections:
        #     view.sel().add(sel)
        # if 'patch' in G.PERMS:
        #     view.set_read_only(False)
        # else:
        #     view.set_status('Floobits', 'You don\'t have write permission. Buffer is read-only.')
        #     view.set_read_only(True)
