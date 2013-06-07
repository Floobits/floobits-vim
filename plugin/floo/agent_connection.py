import os
import json
import socket
import Queue
import sys
import select
import time

ssl = False
try:
    import ssl
except ImportError:
    pass

import vim

import msg
import sublime
import shared as G


CERT = os.path.join(vim.eval("g:floobits_plugin_dir"), 'startssl-ca.pem')
msg.debug("CERT is ", CERT)


class AgentConnection(object):
    ''' Simple chat server using select '''
    def __init__(self, owner, room, host=None, port=None, secure=True, on_auth=None, Protocol=None):
        self.sock_q = Queue.Queue()
        self.sock = None
        self.net_buf = ''
        self.reconnect_delay = G.INITIAL_RECONNECT_DELAY
        self.reconnect_timeout = None
        self.username = G.USERNAME
        self.secret = G.SECRET
        self.authed = False
        self.host = host or G.DEFAULT_HOST
        self.port = port or G.DEFAULT_PORT
        self.secure = secure
        self.owner = owner
        self.room = room
        self.retries = G.MAX_RETRIES
        self._on_auth = on_auth
        self.empty_selects = 0
        self.room_info = {}
        self.protocol = Protocol(self)

    def tick(self):
        self.protocol.push()
        self.select()

    def send_get_buf(self, buf_id):
        req = {
            'name': 'get_buf',
            'id': buf_id
        }
        self.put(req)

    def send_auth(self):
        # TODO: we shouldn't throw away all of this
        self.sock_q = Queue.Queue()
        self.put({
            'username': self.username,
            'secret': self.secret,
            'room': self.room,
            'room_owner': self.owner,
            'client': self.protocol.CLIENT,
            'platform': sys.platform,
            'version': G.__VERSION__
        })

    def send_msg(self, msg):
        self.put({'name': 'msg', 'data': msg})
        self.protocol.chat(self.username, time.time(), msg, True)

    def on_auth(self):
        self.authed = True
        self.retries = G.MAX_RETRIES
        msg.log('Successfully joined room %s/%s' % (self.owner, self.room))
        if self._on_auth:
            self._on_auth(self)
            self._on_auth = None

    def stop(self, log=True):
        if log:
            msg.log('Disconnecting from room %s/%s' % (self.owner, self.room))
        sublime.cancel_timeout(self.reconnect_timeout)
        self.reconnect_timeout = None
        try:
            self.retries = -1
            self.sock.shutdown(2)
            self.sock.close()
        except Exception:
            return False
        if log:
            msg.log('Disconnected.')
        return True

    def is_ready(self):
        return self.authed

    def put(self, item):
        if not item:
            return
        self.sock_q.put(json.dumps(item) + '\n')
        qsize = self.sock_q.qsize()
        if qsize > 0:
            msg.debug('%s items in q' % qsize)

    def reconnect(self):
        if self.reconnect_timeout:
            return
        try:
            self.sock.close()
        except Exception:
            pass
        self.room_info = {}
        self.net_buf = ''
        self.sock = None
        self.authed = False
        self.reconnect_delay *= 1.5
        if self.reconnect_delay > 10000:
            self.reconnect_delay = 10000
        if self.retries > 0:
            msg.log('Floobits: Reconnecting in %sms' % self.reconnect_delay)
            self.reconnect_timeout = sublime.set_timeout(self.connect, int(self.reconnect_delay))
        elif self.retries == 0:
            msg.error('Floobits Error! Too many reconnect failures. Giving up.')
        self.retries -= 1

    def connect(self, cb=None):
        self.stop(False)
        self.empty_selects = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if self.secure:
            if ssl:  # ST2 on linux doesn't have the ssl module. Not sure about windows
                self.sock = ssl.wrap_socket(self.sock, ca_certs=CERT, cert_reqs=ssl.CERT_REQUIRED)
            else:
                msg.debug('No SSL module found. Connection will not be encrypted.')
                if self.port == G.DEFAULT_PORT:
                    self.port = 3148  # plaintext port
        msg.debug('Connecting to %s:%s' % (self.host, self.port))
        try:
            self.sock.connect((self.host, self.port))
            if self.secure and ssl:
                self.sock.do_handshake()
        except socket.error as e:
            msg.error('Error connecting:', e)
            self.reconnect()
            return
        self.sock.setblocking(0)
        msg.debug('Connected!')
        self.reconnect_delay = G.INITIAL_RECONNECT_DELAY
        self.send_auth()
        if cb:
            cb()

    def _get_from_queue(self):
        while True:
            try:
                yield self.sock_q.get_nowait()
            except Queue.Empty:
                break

    def handle(self, req):
        self.net_buf += req
        new_data = False
        while True:
            before, sep, after = self.net_buf.partition('\n')
            if not sep:
                break
            try:
                data = json.loads(before)
            except Exception as e:
                msg.error('Unable to parse json:', e)
                msg.error('Data:', before)
                raise e
            self.protocol.handle(data)
            new_data = True
            self.net_buf = after
        #XXX move to protocol :(
        if new_data:
            vim.command('redraw')

    def select(self):
        if not self.sock:
            msg.error('select(): No socket.')
            return self.reconnect()

        try:
            _in, _out, _except = select.select([self.sock], [self.sock], [self.sock], 0)
        except (select.error, socket.error, Exception) as e:
            msg.error('Error in select(): %s' % str(e))
            return self.reconnect()

        if _except:
            msg.error('Socket error')
            return self.reconnect()

        if _in:
            buf = ''
            while True:
                try:
                    d = self.sock.recv(4096)
                    if not d:
                        break
                    buf += d
                except (socket.error, TypeError):
                    break
            if buf:
                self.empty_selects = 0
                self.handle(buf)
            else:
                self.empty_selects += 1
                if self.empty_selects > 10:
                    msg.error('No data from sock.recv() {0} times.'.format(self.empty_selects))
                    return self.reconnect()

        if _out:
            for p in self._get_from_queue():
                if p is None:
                    self.sock_q.task_done()
                    continue
                try:
                    self.sock.sendall(p)
                    self.sock_q.task_done()
                except Exception as e:
                    msg.error('Couldn\'t write to socket: %s' % str(e))
                    return self.reconnect()
