"""Understands the floobits protocol"""

import os
import hashlib
import collections
import Queue

from lib import diff_match_patch as dmp

import msg
import shared as G
import utils
import sublime


def buf_populated(func):
    def wrapped(self, data):
        if data.get('id') is None:
            msg.debug('no buf id in data')
            return
        buf = self.FLOO_BUFS.get(data['id'])
        if buf is None or 'buf' not in buf:
            msg.debug('buf is not populated yet')
            return
        func(self, data)
    return wrapped


class BaseProtocol(object):
    BUFS_CHANGED = []
    SELECTION_CHANGED = []
    MODIFIED_EVENTS = Queue.Queue()
    SELECTED_EVENTS = Queue.Queue()
    FLOO_BUFS = {}

    def __init__(self, agent):
        self.agent = agent
        self.perms = []
        self.follow_mode = False
        self.chat_deck = collections.deque(maxlen=10)

    def get_view(self, data):
        raise NotImplemented()

    def update_view(self, data):
        raise NotImplemented()

    def get_buf(self, data):
        raise NotImplemented()

    def save_buf(self, data):
        raise NotImplemented()

    def delete_buf(self, data):
        raise NotImplemented()

    def chat(self, data):
        raise NotImplemented()

    def maybe_buffer_changed(self):
        raise NotImplemented()

    def maybe_selection_changed(self):
        raise NotImplemented()

    def on_msg(self, data):
        raise NotImplemented()

    def follow(self, follow_mode=None):
        if follow_mode is None:
            follow_mode = not self.follow_mode
        self.follow_mode = follow_mode
        msg.log('follow mode is %s' % {True: 'enabled', False: 'disabled'}[self.follow_mode])

    def create_buf(self, path):
        if not utils.is_shared(path):
            msg.error('Skipping adding %s because it is not in shared path %s.' % (path, G.PROJECT_PATH))
            return
        if os.path.isdir(path):
            for dirpath, dirnames, filenames in os.walk(path):
                # Don't care about hidden stuff
                dirnames[:] = [d for d in dirnames if d[0] != '.']
                for f in filenames:
                    f_path = os.path.join(dirpath, f)
                    if f[0] == '.':
                        msg.log('Not creating buf for hidden file %s' % f_path)
                    else:
                        sublime.set_timeout(self.create_buf, 0, f_path)
            return
        try:
            buf_fd = open(path, 'rb')
            buf = buf_fd.read().decode('utf-8')
            rel_path = utils.to_rel_path(path)
            msg.log('creating buffer ', rel_path)
            event = {
                'name': 'create_buf',
                'buf': buf,
                'path': rel_path,
            }
            self.agent.put(event)
        except (IOError, OSError):
            msg.error('Failed to open %s.' % path)
        except Exception as e:
            msg.error('Failed to create buffer %s: %s' % (path, str(e)))

    def handle(self, data):
        name = data.get('name')
        if not name:
            return msg.error('no name in data?!?')
        func = getattr(self, "on_%s" % (name))
        if not func:
            return msg.error('unknown name!', name, 'data:', data)
        func(data)

    def push(self):
        reported = set()
        while self.BUFS_CHANGED:
            buf_id = self.BUFS_CHANGED.pop()
            view = self.get_view(buf_id)
            buf = view.buf
            if view.is_loading():
                msg.debug('View for buf %s is not ready. Ignoring change event' % buf['id'])
                continue
            if 'patch' not in self.perms:
                continue
            vb_id = view.native_id
            if vb_id in reported:
                continue
            if 'buf' not in buf:
                msg.debug('No data for buf %s %s yet. Skipping sending patch' % (buf['id'], buf['path']))
                continue

            reported.add(vb_id)
            patch = utils.FlooPatch(view)
            # Update the current copy of the buffer
            buf['buf'] = patch.current
            buf['md5'] = hashlib.md5(patch.current.encode('utf-8')).hexdigest()
            self.agent.put(patch.to_json())

        while self.SELECTION_CHANGED:
            view, ping = self.SELECTION_CHANGED.pop()
            # consume highlight events to avoid leak
            if 'highlight' not in self.perms:
                continue
            vb_id = view.native_id
            if vb_id in reported:
                continue

            reported.add(vb_id)
            highlight_json = {
                'id': view.buf['id'],
                'name': 'highlight',
                'ranges': view.get_selections(),
                'ping': ping,
            }
            self.agent.put(highlight_json)

    def on_create_buf(self, data):
        self.on_get_buf(data)

    def on_get_buf(self, data):
        buf_id = data['id']
        self.FLOO_BUFS[buf_id] = data
        view = self.get_view(buf_id)
        if view:
            self.update_view(data, view)
        else:
            self.save_buf(data)

    def on_rename_buf(self, data):
        new = utils.get_full_path(data['path'])
        old = utils.get_full_path(data['old_path'])
        new_dir = os.path.dirname(new)
        if new_dir:
            utils.mkdir(new_dir)
        os.rename(old, new)
        view = self.get_view(data['id'])
        if view:
            view.rename(new)

    def on_room_info(self, data):
        # Success! Reset counter
        self.room_info = data
        self.perms = data['perms']

        if 'patch' not in data['perms']:
            msg.log('We don\'t have patch permission. Setting buffers to read-only')

        utils.mkdir(G.PROJECT_PATH)

        for buf_id, buf in data['bufs'].iteritems():
            buf_id = int(buf_id)  # json keys must be strings
            buf_path = utils.get_full_path(buf['path'])
            new_dir = os.path.dirname(buf_path)
            utils.mkdir(new_dir)
            open(buf_path, "a")
            self.FLOO_BUFS[buf_id] = buf
            self.agent.send_get_buf(buf_id)
        msg.debug(G.PROJECT_PATH)

        self.agent.on_auth()

    def on_join(self, data):
        msg.log('%s joined the room' % data['username'])

    def on_part(self, data):
        msg.log('%s left the room' % data['username'])
        region_key = 'floobits-highlight-%s' % (data['user_id'])
        for window in sublime.windows():
            for view in window.views():
                view.erase_regions(region_key)

    @buf_populated
    def on_patch(self, data):
        buf_id = data['id']
        buf = self.FLOO_BUFS[buf_id]
        view = self.get_view(buf_id)
        DMP = dmp.diff_match_patch()
        if len(data['patch']) == 0:
            msg.error('wtf? no patches to apply. server is being stupid')
            return
        msg.debug('patch is', data['patch'])
        dmp_patches = DMP.patch_fromText(data['patch'])
        # TODO: run this in a separate thread
        if view:
            old_text = view.get_text()
        else:
            old_text = buf.get('buf', '')
        md5_before = hashlib.md5(old_text.encode('utf-8')).hexdigest()
        if md5_before != data['md5_before']:
            msg.debug('maybe vim is lame and discarded a trailing newline')
            old_text += '\n'
        md5_before = hashlib.md5(old_text.encode('utf-8')).hexdigest()
        if md5_before != data['md5_before']:
            msg.warn('starting md5s don\'t match for %s. ours: %s patch: %s this is dangerous!' %
                    (buf['path'], md5_before, data['md5_before']))

        t = DMP.patch_apply(dmp_patches, old_text)

        clean_patch = True
        for applied_patch in t[1]:
            if not applied_patch:
                clean_patch = False
                break

        if G.DEBUG:
            if len(t[0]) == 0:
                msg.debug('OMG EMPTY!')
                msg.debug('Starting data:', buf['buf'])
                msg.debug('Patch:', data['patch'])
            if '\x01' in t[0]:
                msg.debug('FOUND CRAZY BYTE IN BUFFER')
                msg.debug('Starting data:', buf['buf'])
                msg.debug('Patch:', data['patch'])

        if not clean_patch:
            msg.error('failed to patch %s cleanly. re-fetching buffer' % buf['path'])
            return self.agent.send_get_buf(buf_id)

        cur_hash = hashlib.md5(t[0].encode('utf-8')).hexdigest()
        if cur_hash != data['md5_after']:
            msg.warn(
                '%s new hash %s != expected %s. re-fetching buffer...' %
                (buf['path'], cur_hash, data['md5_after'])
            )
            return self.agent.send_get_buf(buf_id)

        buf['buf'] = t[0]
        buf['md5'] = cur_hash

        if not view:
            self.save_buf(buf)
            return
        view.apply_patches(buf, t)

    def on_delete_buf(self, data):
        #used to take path
        path = utils.get_full_path(data['path'])
        utils.rm(path)
        self.delete_buf(data['id'])

        if not utils.is_shared(path):
            msg.error('Skipping deleting %s because it is not in shared path %s.' % (path, G.PROJECT_PATH))
            return
        if os.path.isdir(path):
            for dirpath, dirnames, filenames in os.walk(path):
                # Don't care about hidden stuff
                dirnames[:] = [d for d in dirnames if d[0] != '.']
                for f in filenames:
                    f_path = os.path.join(dirpath, f)
                    if f[0] == '.':
                        msg.log('Not deleting buf for hidden file %s' % f_path)
                    else:
                        self.delete_buf(f_path)
            return
        buf_to_delete = None
        rel_path = utils.to_rel_path(path)
        for buf_id, buf in self.FLOO_BUFS.items():
            if rel_path == buf['path']:
                buf_to_delete = buf
                break
        if buf_to_delete is None:
            msg.error('%s is not in this room' % path)
            return
        msg.log('deleting buffer ', rel_path)
        event = {
            'name': 'delete_buf',
            'id': buf_to_delete['id'],
        }
        self.agent.put(event)

    @buf_populated
    def on_highlight(self, data):
        #     floobits.highlight(data['id'], region_key, data['username'], data['ranges'], data.get('ping', False))
        #buf_id, region_key, username, ranges, ping=False):
        ping = data.get('ping', False)
        if self.follow_mode:
            ping = True
        buf = self.FLOO_BUFS[data['id']]
        view = self.get_view(data['id'])
        if not view:
            if not ping:
                return
            view = self.create_view(buf)
            if not view:
                return
        if ping:
            try:
                offset = data['ranges'][0][0]
            except IndexError as e:
                msg.debug('could not get offset from range %s' % e)
            else:
                msg.log('You have been summoned by %s' % (data.get('username', 'an unknown user')))
                view.set_cursor_position(offset)
        view.highlight(data['ranges'], data['user_id'])

    def on_error(self, data):
        message = 'Floobits: Error! Message: %s' % str(data.get('msg'))
        msg.error(message)

    def on_disconnect(self, data):
        message = 'Floobits: Disconnected! Reason: %s' % str(data.get('reason'))
        msg.error(message)
        sublime.error_message(message)
        self.agent.stop()
