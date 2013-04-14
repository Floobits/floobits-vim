import os
import Queue
import json
import hashlib
from datetime import datetime

import vim
import sublime

import msg
import shared as G
import utils


def set_agent(agent):
    Listener.agent = agent


class Listener(object):

    def __init__(self):
        self.between_save_events = {}

    def id(self, view):
        return view.buffer_id()

    def name(self, view):
        return view.file_name()

    def on_new(self, view):
        msg.debug('new', self.name(view))

    def on_clone(self, view):
        msg.debug('clone', self.name(view))

    def on_load(self, view):
        msg.debug('load', self.name(view))

    def on_pre_save(self, view):
        p = view.name()
        if view.file_name():
            p = utils.to_rel_path(view.file_name())
        self.between_save_events[view.buffer_id()] = p

    def on_post_save(self, view):
        def cleanup():
            del self.between_save_events[view.buffer_id()]
        if view == G.CHAT_VIEW or view.file_name() == G.CHAT_VIEW_PATH:
            return cleanup()
        else:
            print G.CHAT_VIEW_PATH, "not", view.file_name()
        event = None
        buf = get_buf(view)
        name = utils.to_rel_path(view.file_name())
        old_name = self.between_save_events[view.buffer_id()]

        if buf is None:
            if utils.is_shared(view.file_name()):
                msg.log('new buffer ', name, view.file_name())
                event = {
                    'name': 'create_buf',
                    'buf': get_text(view),
                    'path': name
                }
        elif name != old_name:
            if utils.is_shared(view.file_name()):
                msg.log('renamed buffer {0} to {1}'.format(old_name, name))
                event = {
                    'name': 'rename_buf',
                    'id': buf['id'],
                    'path': name
                }
            else:
                msg.log('deleting buffer from shared: {0}'.format(name))
                event = {
                    'name': 'delete_buf',
                    'id': buf['id'],
                }

        if event and Listener.agent:
            Listener.agent.put(json.dumps(event))

        cleanup()

    def on_modified(self, buf_num):
        try:
            MODIFIED_EVENTS.get_nowait()
        except Queue.Empty:
            self.add(buf_num)
        else:
            MODIFIED_EVENTS.task_done()

    def on_selection_modified(self, buf_num):
        try:
            SELECTED_EVENTS.get_nowait()
        except Queue.Empty:
            buf = get_buf(buf_num)
            if buf:
                msg.debug('selection in view %s, buf id %s' % (buf['path'], buf['id']))
                self.selection_changed.append((buf, False))
        else:
            SELECTED_EVENTS.task_done()

    def on_activated(self, view):
        self.add(view)

    def add(self, view):
        buf = get_buf(view)
        if buf:
            msg.debug('changed view %s buf id %s' % (buf['path'], buf['id']))
            self.BUFS_CHANGED.append((view, buf))
