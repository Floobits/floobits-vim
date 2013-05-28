"""Understands the floobits protocol"""

import os
import json
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
        self.ignored_names = ['node_modules']

    def get_view(self, data):
        raise NotImplemented()

    def update_view(self, data):
        raise NotImplemented()

    def get_buf(self, data):
        raise NotImplemented()

    def get_buf_by_path(self, path):
        rel_path = utils.to_rel_path(path)
        for buf_id, buf in self.FLOO_BUFS.iteritems():
            if rel_path == buf['path']:
                return buf
        return None

    def save_buf(self, data):
        raise NotImplemented()

    def chat(self, data):
        raise NotImplemented()

    def maybe_buffer_changed(self):
        raise NotImplemented()

    def maybe_selection_changed(self):
        raise NotImplemented()

    def on_msg(self, data):
        raise NotImplemented()

    def is_shared(self, p):
        if not self.agent.is_ready():
            msg.debug('agent is not ready. %s is not shared' % p)
            return False
        p = utils.unfuck_path(p)
        # TODO: tokenize on path seps and then look for ..
        if utils.to_rel_path(p).find("../") == 0:
            return False
        return True

    def follow(self, follow_mode=None):
        if follow_mode is None:
            follow_mode = not self.follow_mode
        self.follow_mode = follow_mode
        msg.log('follow mode is %s' % {True: 'enabled', False: 'disabled'}[self.follow_mode])

    def create_buf(self, path, force=False):
        if G.SPARSE_MODE and not force:
            msg.debug("Skipping %s because user enabled sparse mode." % path)
            return
        if 'create_buf' not in self.perms:
            msg.error("Skipping %s. You don't have permission to create buffers in this room." % path)
            return
        if not self.is_shared(path):
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
                        continue
                    if f in self.ignored_names:
                        # TODO: prompt instead of being lame
                        msg.log('Not creating buf for ignored file %s' % f_path)
                        continue
                    sublime.set_timeout(self.create_buf, 0, f_path, force)
            return

        if self.get_buf_by_path(path):
            msg.debug('Buf %s already exists in room. Skipping adding.' % path)
            return

        try:
            buf_fd = open(path, 'rb')
            buf = buf_fd.read().decode('utf-8')
            rel_path = utils.to_rel_path(path)
            msg.debug('creating buffer ', rel_path)
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
        func = getattr(self, "on_%s" % (name), None)
        if not func:
            return msg.debug('unknown name', name, 'data:', data)
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
        view = self.get_view(data['id'])
        self.FLOO_BUFS[data['id']]['path'] = data['path']
        if view:
            view.rename(new)
        else:
            os.rename(old, new)

    def on_room_info(self, data):
        # Success! Reset counter
        self.room_info = data
        self.perms = data['perms']

        if 'patch' not in data['perms']:
            msg.log('We don\'t have patch permission. Setting buffers to read-only')

        utils.mkdir(G.PROJECT_PATH)

        floo_json = {
            'url': utils.to_room_url({
                'host': self.agent.host,
                'owner': self.agent.owner,
                'port': self.agent.port,
                'room': self.agent.room,
                'secure': self.agent.secure,
            })
        }
        with open(os.path.join(G.PROJECT_PATH, '.floo'), 'w') as floo_fd:
            floo_fd.write(json.dumps(floo_json, indent=4, sort_keys=True))

        for buf_id, buf in data['bufs'].iteritems():
            buf_id = int(buf_id)  # json keys must be strings
            buf_path = utils.get_full_path(buf['path'])
            new_dir = os.path.dirname(buf_path)
            utils.mkdir(new_dir)
            self.FLOO_BUFS[buf_id] = buf
            try:
                buf_fd = open(buf_path, 'r')
                buf_buf = buf_fd.read().decode('utf-8')
                md5 = hashlib.md5(buf_buf.encode('utf-8')).hexdigest()
                if md5 == buf['md5']:
                    msg.debug('md5 sums match. not getting buffer')
                    buf['buf'] = buf_buf
                else:
                    raise Exception('different md5')
            except Exception:
                try:
                    open(buf_path, "a").close()
                except Exception as e:
                    msg.debug("couldn't touch file: %s becuase %s" % (buf_path, e))
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
        added_newline = False
        buf_id = data['id']
        buf = self.FLOO_BUFS[buf_id]
        view = self.get_view(buf_id)
        DMP = dmp.diff_match_patch()
        if len(data['patch']) == 0:
            msg.error('wtf? no patches to apply. server is being stupid')
            return
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
            added_newline = True
        md5_before = hashlib.md5(old_text.encode('utf-8')).hexdigest()
        if md5_before != data['md5_before']:
            msg.warn('starting md5s don\'t match for %s. ours: %s patch: %s this is dangerous!' %
                    (buf['path'], md5_before, data['md5_before']))
            if added_newline:
                old_text = old_text[:-1]
                md5_before = hashlib.md5(old_text.encode('utf-8')).hexdigest()

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

    def delete_buf(self, path):
        """deletes a path"""

        if not path:
            return

        path = utils.get_full_path(path)

        if not self.is_shared(path):
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
    def on_delete_buf(self, data):
        # TODO: somehow tell the user about this. maybe delete on disk too?
        del self.FLOO_BUFS[data['id']]
        path = utils.get_full_path(data['path'])
        if not G.DELETE_LOCAL_FILES:
            msg.log('Not deleting %s because delete_local_files is disabled' % path)
            return
        utils.rm(path)
        msg.warn('deleted %s because %s told me to.' % (path, data.get('username', 'the internet')))

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
                view.focus()
                view.set_cursor_position(offset)
        if G.SHOW_HIGHLIGHTS:
            view.highlight(data['ranges'], data['user_id'])

    def on_error(self, data):
        message = 'Floobits: Error! Message: %s' % str(data.get('msg'))
        msg.error(message)

    def on_disconnect(self, data):
        message = 'Floobits: Disconnected! Reason: %s' % str(data.get('reason'))
        msg.error(message)
        msg.error(message)
        self.agent.stop()
