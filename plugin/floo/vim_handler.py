import os
import time
import hashlib
import collections

try:
    import ssl
    assert ssl
except ImportError:
    ssl = False

try:
    unicode()
except NameError:
    unicode = str

import vim

try:
    from . import editor
    from .common import msg, shared as G, utils
    from .view import View
    from .common.handlers import floo_handler
    assert G and msg and utils
except ImportError:
    from floo import editor
    from common import msg, shared as G, utils
    from common.handlers import floo_handler
    from view import View


def get_buf(view):
    if not (G.AGENT and G.AGENT.is_ready()):
        return
    return G.AGENT.get_buf_by_path(view.file_name())


def send_summon(buf_id, sel):
    highlight_json = {
        'id': buf_id,
        'name': 'highlight',
        'ranges': sel,
        'ping': True,
        'summon': True,
    }
    if G.AGENT and G.AGENT.is_ready():
        G.AGENT.send(highlight_json)


class VimHandler(floo_handler.FlooHandler):
    def __init__(self, *args, **kwargs):
        super(VimHandler, self).__init__(*args, **kwargs)
        self.user_highlights = {}

    def tick(self):
        reported = set()
        while self.views_changed:
            v, buf = self.views_changed.pop()
            if not G.JOINED_WORKSPACE:
                msg.debug('Not connected. Discarding view change.')
                continue
            if 'patch' not in G.PERMS:
                continue
            if 'buf' not in buf:
                msg.debug('No data for buf %s %s yet. Skipping sending patch' % (buf['id'], buf['path']))
                continue
            view = View(v, buf)
            if view.is_loading():
                msg.debug('View for buf %s is not ready. Ignoring change event' % buf['id'])
                continue
            if view.native_id in reported:
                continue
            reported.add(view.native_id)
            patch = utils.FlooPatch(view.get_text(), buf)
            # Update the current copy of the buffer
            buf['buf'] = patch.current
            buf['md5'] = hashlib.md5(patch.current.encode('utf-8')).hexdigest()
            self.send(patch.to_json())

        reported = set()
        while self.selection_changed:
            v, buf, summon = self.selection_changed.pop()

            if not G.JOINED_WORKSPACE:
                msg.debug('Not connected. Discarding selection change.')
                continue
            # consume highlight events to avoid leak
            if 'highlight' not in G.PERMS:
                continue

            view = View(v, buf)
            vb_id = view.native_id
            if vb_id in reported:
                continue

            reported.add(vb_id)
            highlight_json = {
                'id': buf['id'],
                'name': 'highlight',
                'ranges': view.get_selections(),
                'ping': summon,
                'summon': summon,
            }
            self.send(highlight_json)

    def maybe_selection_changed(self, vim_buf, is_ping):
        buf = self.get_buf_by_path(vim_buf.name)
        if not buf:
            msg.debug('no buffer found for view %s' % vim_buf.number)
            return
        view = self.get_view(buf['id'])
        msg.debug("selection changed: %s %s %s" % (vim_buf.number, buf['id'], view))
        self.selection_changed.append([vim_buf, buf, is_ping])

    def maybe_buffer_changed(self, vim_buf):
        text = vim_buf[:]
        buf = self.get_buf_by_path(vim_buf.name)
        if not buf or 'buf' not in buf:
            return

        if buf['buf'] != text:
            self.views_changed.append([vim_buf, buf])

    def create_view(self, buf):
        path = utils.save_buf(buf)
        vb = self.get_vim_buf_by_path(buf['path'])
        if vb:
            return View(vb, buf)

        vim.command(':edit! %s' % path)
        vb = self.get_vim_buf_by_path(buf['path'])
        if vb is None:
            msg.debug('vim buffer is none even though we tried to open it: %s' % path)
            return
        return View(vb, buf)

    def save_buf(self, buf):
        path = utils.get_full_path(buf['path'])
        utils.mkdir(os.path.split(path)[0])
        with open(path, 'wb') as fd:
            if buf['encoding'] == 'utf8':
                fd.write(buf['buf'].encode('utf-8'))
            else:
                fd.write(buf['buf'])
        return path

    def update_view(self, buf, view=None):
        msg.debug('updating view for buf %s' % buf['id'])
        view = view or self.get_view(buf['id'])
        if not view:
            msg.log('view for buf %s not found. not updating' % buf['id'])
            return
        self.MODIFIED_EVENTS.put(1)
        view.set_text(buf['buf'])

    def ok_cancel_dialog(self, msg, cb=None):
        res = editor.ok_cancel_dialog(msg)
        return (cb and cb(res) or res)

    def get_vim_buf_by_path(self, p):
        for vim_buf in vim.buffers:
            if vim_buf.name and p == utils.to_rel_path(vim_buf.name):
                return vim_buf
        return None

    def get_view(self, buf_id):
        buf = self.bufs.get(buf_id)
        if not buf:
            return None

        vb = self.get_vim_buf_by_path(buf['path'])
        if not vb:
            return None

        if vim.eval('bufloaded(%s)' % vb.number) == '0':
            return None

        return View(vb, buf)

    def save_view(self, view):
        self.ignored_saves[view.native_id] += 1
        view.save()

    def reset(self):
        super(self.__class__, self).reset()
        self.on_load = {}
        self.on_clone = {}
        self.create_buf_cbs = {}
        self.temp_disable_stalk = False
        self.temp_ignore_highlight = {}
        self.temp_ignore_highlight = {}
        self.views_changed = []
        self.selection_changed = []
        self.ignored_saves = collections.defaultdict(int)
        self.chat_deck = collections.deque(maxlen=10)

    def send_msg(self, msg):
        self.send({'name': 'msg', 'data': msg})
        self.chat(self.username, time.time(), msg, True)

    def chat(self, username, timestamp, message, self_msg=False):
        envelope = msg.MSG(message, timestamp, username)
        if not self_msg:
            self.chat_deck.appendleft(envelope)
        envelope.display()

    def prompt_join_hangout(self, hangout_url):
        hangout_client = None
        users = self.workspace_info.get('users')
        for user_id, user in users.items():
            if user['username'] == G.USERNAME and 'hangout' in user['client']:
                hangout_client = user
                break
        if not hangout_client:
            G.WORKSPACE_WINDOW.run_command('floobits_prompt_hangout', {'hangout_url': hangout_url})

    def on_msg(self, data):
        timestamp = data.get('time') or time.time()
        msg.log('[%s] <%s> %s' % (time.ctime(timestamp), data.get('username', ''), data.get('data', '')))

    def get_username_by_id(self, user_id):
        try:
            return self.workspace_info['users'][str(user_id)]['username']
        except Exception:
            return ''

    def get_buf(self, buf_id, view=None):
        req = {
            'name': 'get_buf',
            'id': buf_id
        }
        buf = self.bufs[buf_id]
        msg.warn('Syncing buffer %s for consistency.' % buf['path'])
        if 'buf' in buf:
            del buf['buf']
        if view:
            view.set_read_only(True)
            view.set_status('Floobits', 'Floobits locked this file until it is synced.')
        G.AGENT.send(req)

    def delete_buf(self, path):
        if not utils.is_shared(path):
            msg.error('Skipping deleting %s because it is not in shared path %s.' % (path, G.PROJECT_PATH))
            return
        if os.path.isdir(path):
            for dirpath, dirnames, filenames in os.walk(path):
                # TODO: rexamine this assumption
                # Don't care about hidden stuff
                dirnames[:] = [d for d in dirnames if d[0] != '.']
                for f in filenames:
                    f_path = os.path.join(dirpath, f)
                    if f[0] == '.':
                        msg.log('Not deleting buf for hidden file %s' % f_path)
                    else:
                        self.delete_buf(f_path)
            return
        buf_to_delete = self.get_buf_by_path(path)
        if buf_to_delete is None:
            msg.error('%s is not in this workspace' % path)
            return
        msg.log('deleting buffer ', utils.to_rel_path(path))
        event = {
            'name': 'delete_buf',
            'id': buf_to_delete['id'],
        }
        G.AGENT.send(event)

    def highlight(self, buf_id, region_key, username, ranges, summon, clone):
        return

    def clear_highlights(self, view):
        if not G.AGENT:
            return
        buf = get_buf(view)
        if not buf:
            return
        msg.debug('clearing highlights in %s, buf id %s' % (buf['path'], buf['id']))
        for user_id, username in G.AGENT.workspace_info['users'].items():
            view.clear_highlight(user_id)

    def summon(self, view):
        buf = get_buf(view)
        if buf:
            msg.debug('summoning selection in view %s, buf id %s' % (buf['path'], buf['id']))
            self.selection_changed.append((view, buf, True))
        else:
            path = view.file_name()
            if not utils.is_shared(path):
                editor.error_message('Can\'t summon because %s is not in shared path %s.' % (path, G.PROJECT_PATH))
                return
            share = editor.ok_cancel_dialog('This file isn\'t shared. Would you like to share it?', 'Share')
            if share:
                sel = [[x.a, x.b] for x in view.sel()]
                self.create_buf_cbs[utils.to_rel_path(path)] = lambda buf_id: send_summon(buf_id, sel)
                self.upload(path)

    def _on_room_info(self, data):
        super(VimHandler, self)._on_room_info(data)
        vim.command(':Explore %s | redraw' % G.PROJECT_PATH)

    def _on_delete_buf(self, data):
        # TODO: somehow tell the user about this
        buf_id = data['id']
        view = self.get_view(buf_id)
        try:
            if view:
                view = view.view
                view.set_scratch(True)
                G.WORKSPACE_WINDOW.focus_view(view)
                G.WORKSPACE_WINDOW.run_command("close_file")
        except Exception as e:
            msg.debug('Error closing view: %s' % unicode(e))
        try:
            buf = self.bufs.get(buf_id)
            if buf:
                del self.paths_to_ids[buf['path']]
                del self.bufs[buf_id]
        except KeyError:
            msg.debug('KeyError deleting buf id %s' % buf_id)
        super(self.__class__, self)._on_delete_buf(data)

    def _on_create_buf(self, data):
        super(self.__class__, self)._on_create_buf(data)
        cb = self.create_buf_cbs.get(data['path'])
        if not cb:
            return
        del self.create_buf_cbs[data['path']]
        try:
            cb(data['id'])
        except Exception as e:
            print(e)

    def _on_part(self, data):
        super(self.__class__, self)._on_part(data)
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

    def _on_highlight(self, data):
        region_key = 'floobits-highlight-%s' % (data['user_id'])
        self.highlight(data['id'], region_key, data['username'], data['ranges'], data.get('ping', False), True)
