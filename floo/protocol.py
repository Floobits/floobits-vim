"""Understands the floobits protocol"""

import os
import json
import hashlib
import datetime
import collections
from queue import Queue

from lib import diff_match_patch as dmp

import msg
import shared as G
import utils
import sublime


def create_buf(self, data):
    self.FLOO_BUFS[data['id']] = data
    self.save_buf(data)


class BaseProtocol(object):
    VIEWS_CHANGED = []
    SELECTION_CHANGED = []
    MODIFIED_EVENTS = Queue.Queue()
    SELECTED_EVENTS = Queue.Queue()
    FLOO_BUFS = {}
    VIM_TO_FLOO_ID = {}

    def __init__(self, agent):
        self.agent = agent
        self.perms = []
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

    def handle(self, data):
        name = data.get('name')
        if not name:
            return msg.error('no name in data?!?')
        func = getattr(self, "on_%s" % (name))
        if not func:
            return msg.error('unknown name!', name, 'data:', data)
        func(data)

    def on_get_buf(self, data):
        buf_id = data['id']
        self.FLOO_BUFS[buf_id] = data
        view = self.get_view(buf_id)
        if view:
            self.update_view(data, view)
        else:
            self.save_buf(data)

    def on_create_buf(self, path):
        # >>> (lambda x: lambda: x)(2)()
        # TODO: check if functools can do this in st2
        #  really_create_buf = lambda x: (lambda: self.create_buf(x))
        def really_create_buf(x):
            return (lambda: self.create_buf(x))
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
                        sublime.set_timeout(really_create_buf(f_path), 0)
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
            self.agent.put(json.dumps(event))
        except (IOError, OSError):
            msg.error('Failed to open %s.' % path)
        except Exception as e:
            msg.error('Failed to create buffer %s: %s' % (path, str(e)))

    def on_rename_buf(self, data):
        new = utils.get_full_path(data['path'])
        old = utils.get_full_path(data['old_path'])
        new_dir = os.path.split(new)[0]
        if new_dir:
            utils.mkdir(new_dir)
        os.rename(old, new)
        view = self.get_view(data['id'])
        if view:
            view.retarget(new)

    def on_room_info(self, data):
        # Success! Reset counter
        self.retries = G.MAX_RETRIES
        self.room_info = data
        self.perms = data['perms']

        if 'patch' not in data['perms']:
            msg.log('We don\'t have patch permission. Setting buffers to read-only')

        project_json = {
            'folders': [
                {'path': G.PROJECT_PATH}
            ]
        }

        utils.mkdir(G.PROJECT_PATH)
        with open(os.path.join(G.PROJECT_PATH, '.sublime-project'), 'w') as project_fd:
            project_fd.write(json.dumps(project_json, indent=4, sort_keys=True))

        for buf_id, buf in data['bufs'].iteritems():
            buf_id = int(buf_id)  # json keys must be strings
            new_dir = os.path.split(utils.get_full_path(buf['path']))[0]
            utils.mkdir(new_dir)
            self.FLOO_BUFS[buf_id] = buf
            self.get_buf(buf_id)

        self.agent.on_connect()

    def on_join(self, data):
        msg.log('%s joined the room' % data['username'])

    def on_part(self, data):
        msg.log('%s left the room' % data['username'])
        region_key = 'floobits-highlight-%s' % (data['user_id'])
        for window in sublime.windows():
            for view in window.views():
                view.erase_regions(region_key)

    def push(self):
        reported = set()
        while self.VIEWS_CHANGED:
            view, buf = self.VIEWS_CHANGED.pop()
            if view.is_loading():
                msg.debug('View for buf %s is not ready. Ignoring change event' % buf['id'])
                continue
            if 'patch' not in self.perms:
                continue
            vb_id = view.buffer_id()
            if vb_id in reported:
                continue
            if 'buf' not in buf:
                msg.debug('No data for buf %s %s yet. Skipping sending patch' % (buf['id'], buf['path']))
                continue

            reported.add(vb_id)
            patch = utils.FlooPatch(view, buf)
            # Update the current copy of the buffer
            buf['buf'] = patch.current
            buf['md5'] = hashlib.md5(patch.current.encode('utf-8')).hexdigest()
            self.agent.put(patch.to_json())

        while self.SELECTION_CHANGED:
            view, buf, ping = self.SELECTION_CHANGED.pop()
            # consume highlight events to avoid leak
            if 'highlight' not in self.perms:
                continue
            vb_id = view.buffer_id()
            if vb_id in reported:
                continue

            reported.add(vb_id)
            sel = view.sel()
            highlight_json = json.dumps({
                'id': buf['id'],
                'name': 'highlight',
                'ranges': [[x.a, x.b] for x in sel],
                'ping': ping,
            })
            self.agent.put(highlight_json)

        sublime.set_timeout(self.push, 100)

    def on_patch(self, patch_data):
        buf_id = patch_data['id']
        buf = self.FLOO_BUFS[buf_id]
        view = self.get_view(buf_id)
        DMP = dmp.diff_match_patch()
        if len(patch_data['patch']) == 0:
            msg.error('wtf? no patches to apply. server is being stupid')
            return
        msg.debug('patch is', patch_data['patch'])
        dmp_patches = DMP.patch_fromText(patch_data['patch'])
        # TODO: run this in a separate thread
        if view:
            old_text = self.get_text(view)
        else:
            old_text = buf.get('buf', '')
        md5_before = hashlib.md5(old_text.encode('utf-8')).hexdigest()
        if md5_before != patch_data['md5_before']:
            msg.warn('starting md5s don\'t match for %s. this is dangerous!' % buf['path'])

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
                msg.debug('Patch:', patch_data['patch'])
            if '\x01' in t[0]:
                msg.debug('FOUND CRAZY BYTE IN BUFFER')
                msg.debug('Starting data:', buf['buf'])
                msg.debug('Patch:', patch_data['patch'])

        if not clean_patch:
            msg.error('failed to patch %s cleanly. re-fetching buffer' % buf['path'])
            return self.get_buf(buf_id)

        cur_hash = hashlib.md5(t[0].encode('utf-8')).hexdigest()
        if cur_hash != patch_data['md5_after']:
            msg.warn(
                '%s new hash %s != expected %s. re-fetching buffer...' %
                (buf['path'], cur_hash, patch_data['md5_after'])
            )
            return self.get_buf(buf_id)

        buf['buf'] = t[0]
        buf['md5'] = cur_hash

        if not view:
            self.save_buf(buf)
            return

        selections = [x for x in view.sel()]  # deep copy
        regions = []
        for patch in t[2]:
            offset = patch[0]
            length = patch[1]
            patch_text = patch[2]
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
        self.agent.put(json.dumps(event))

    def on_ping(self, view):
        buf = self.get_buf(view)
        if buf:
            msg.debug('pinging selection in view %s, buf id %s' % (buf['path'], buf['id']))
            self.selection_changed.append((view, buf, True))

    def on_highlight(self, data):
        #     floobits.highlight(data['id'], region_key, data['username'], data['ranges'], data.get('ping', False))
        #buf_id, region_key, username, ranges, ping=False):
        if G.FOLLOW_MODE:
            ping = True
        buf = self.FLOO_BUFS[data['id']]
        view = self.get_view(data['id'])
        if not view:
            if ping:
                view = self.create_view(buf)
            return
            # TODO: scroll to highlight if we just created the view
        view.highlight(data['ranges'], data['user_id'])

    def on_error(self, data):
        message = 'Floobits: Error! Message: %s' % str(data.get('msg'))
        msg.error(message)

    def on_diconnect(self, data):
        message = 'Floobits: Disconnected! Reason: %s' % str(data.get('reason'))
        msg.error(message)
        sublime.error_message(message)
        self.stop()

    def on_msg(self, data):
        message = data.get('data')
        self.chat(data['username'], data['time'], message)
        window = G.ROOM_WINDOW

        def cb(selected):
            if selected == -1:
                return
            envelope = self.chat_deck[selected]
            window.run_command('floobits_prompt_msg', {'msg': '%s: ' % envelope.username})

        if G.ALERT_ON_MSG and message.find(self.username) >= 0:
            window.show_quick_panel([str(x) for x in self.chat_deck], cb)
