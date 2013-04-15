"""Vim specific logic"""
import os
import vim
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
        return self.vim_buf.id

    def is_loading(self):
        return False

    def get_text(self):
        text = ""
        for line in self.vim_buf:
            # TODO: horrible for Windows and Amiga users
            text += line + "\n"
        return text

    def set_text(self, text):
        self.vim_buf[:] = text

    def apply_patches(self, buf, patches):
        # view.replace(edit, region, patch_text)

        selections = [x for x in view.sel()]  # deep copy
        regions = []
        for patch in t[2]:
            offset = patch[0]
            length = patch[1]
            patch_text = patch[2]
            # TODO: totally not in vim
            region = sublime.Region(offset, offset + length)
            regions.append(region)
            self.MODIFIED_EVENTS.put(1)
            try:
                edit = view.begin_edit()
                view.replace(edit, region, patch_text)
            except:
                raise
            else:
                new_sels = []
                for sel in selections:
                    a = sel.a
                    b = sel.b
                    new_offset = len(patch_text) - length
                    if sel.a > offset:
                        a += new_offset
                    if sel.b > offset:
                        b += new_offset
                    new_sels.append(sublime.Region(a, b))
                selections = [x for x in new_sels]
            finally:
                view.end_edit(edit)
        view.sel().clear()
        region_key = 'floobits-patch-' + patch_data['username']
        view.add_regions(region_key, regions, 'floobits.patch', 'circle', sublime.DRAW_OUTLINED)
        sublime.set_timeout(lambda: view.erase_regions(region_key), 1000)
        for sel in selections:
            self.SELECTED_EVENTS.put(1)
            view.sel().add(sel)

        now = datetime.now()
        view.set_status('Floobits', 'Changed by %s at %s' % (patch_data['username'], now.strftime('%H:%M')))

    def get_selection(self):
        pass

    def highlight(self, ranges, user_id):
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
        pass

    def sel(self):
        return []



# def get_text(view):
#     return view.substr(sublime.Region(0, view.size()))

class Protocol(protocol.BaseProtocol):
    """understands vim"""
    CLIENT = 'VIM'
    VIM_TO_FLOO_ID = {}

    def maybe_changed(self, buf_num):
        buf = vim.current.buffer
        buf_num = vim.eval("bufnr('%')")
        text = buf[:]
        buf = self.get_buf(buf_num)
        if buf['buf'] != text:
            self.BUFS_CHANGED.push(buf['id'])

    def get_view(self, buf_id):
        buf = self.FLOO_BUFS.get(buf_id)
        if not buf:
            return None

        for vim_buf in vim.buffers:
            if buf['path'] == utils.to_rel_path(vim_buf.name):
                return View(vim_buf, buf)
        return None

    def create_view(self, buf):
        raise NotImplemented()
        # path = utils.get_full_path(buf['path'])
        # view = vim.magically_make_file(path)
        # if view:
        #     msg.debug('Created view', view.name() or view.file_name())
        # return view

    def get_buf(self, buf_num):
        try:
            buf = vim.buffers[buf_num]
        except IndexError:
            return None
        if not utils.is_shared(buf.name):
            return None
        buf_id = self.VIM_TO_FLOO_ID.get(buf_num)
        if not buf_id:
            return None
        return self.FLOO_BUFS.get(buf_id)

    def save_buf(self, buf):
        path = utils.get_full_path(buf['path'])
        utils.mkdir(os.path.split(path)[0])
        with open(path, 'wb') as fd:
            fd.write(buf['buf'].encode('utf-8'))

    def delete_buf(self, buf_id):
        # TODO: somehow tell the user about this. maybe delete on disk too?
        del G.FLOO_BUFS[buf_id]
        found = False
        for buf_num, fbuf_id in G.VIM_TO_FLOO_ID.iteritems():
            if fbuf_id == buf_id:
                found = True
                break
        if found:
            del G.VIM_TO_FLOO_ID[buf_num]

    def chat(self, username, timestamp, message, self_msg=False):
        raise NotImplemented()
        # envelope = msg.MSG(message, timestamp, username)
        # if not self_msg:
        #     self.chat_deck.appendleft(envelope)
        # envelope.display()

    def update_view(self, buf, view=None):
        print buf
        return
        view = view or self.get_view(buf['id'])
        self.VIM_TO_FLOO_ID[view.vim_buf.id] = buf['id']

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
