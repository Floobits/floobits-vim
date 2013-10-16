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

from common import cert, msg, shared as G, utils
from vim_protocol import Protocol as VimProtocol


class BaseAgentConnection(object):
    ''' Simple chat server using select '''
    MAX_RETRIES = 20
    INITIAL_RECONNECT_DELAY = 500

    def __init__(self, host=None, port=None, secure=True):
        self.sock_q = Queue.Queue()
        self.sock = None
        self.net_buf = ''
        self.reconnect_delay = self.INITIAL_RECONNECT_DELAY
        self.reconnect_timeout = None
        G.JOINED_WORKSPACE = False

        self.host = host or G.DEFAULT_HOST
        self.port = port or G.DEFAULT_PORT
        self.secure = secure

        self.empty_selects = 0
        self.handshaken = False
        self.cert_path = os.path.join(G.BASE_DIR, 'startssl-ca.pem')
        self.call_select = False
        self.retries = self.MAX_RETRIES
        self.protocol = self.Protocol(self)

    def stop(self, log=True):
        if log:
            msg.log('Disconnecting from workspace %s/%s' % (self.owner, self.workspace))
        utils.cancel_timeout(self.reconnect_timeout)
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

    def put(self, item):
        if not item:
            return
        self.sock_q.put(json.dumps(item) + '\n')
        qsize = self.sock_q.qsize()
        if qsize > 0:
            msg.debug('%s items in q' % qsize)

    def qsize(self):
        return self.sock_q.qsize()

    def reconnect(self):
        if self.reconnect_timeout:
            return
        try:
            self.sock.close()
        except Exception:
            pass
        self.workspace_info = {}
        self.bufs_to_stomp = set()
        self.net_buf = ''
        self.sock = None
        self.authed = False
        G.JOINED_WORKSPACE = False
        self.reconnect_delay *= 1.5
        if self.reconnect_delay > 10000:
            self.reconnect_delay = 10000
        if self.retries > 0:
            msg.log('Floobits: Reconnecting in %sms' % self.reconnect_delay)
            self.reconnect_timeout = utils.set_timeout(self.connect, int(self.reconnect_delay))
        elif self.retries == 0:
            msg.error('Floobits Error! Too many reconnect failures. Giving up.')
        self.retries -= 1

    def connect(self, cb=None):
        utils.cancel_timeout(self.reconnect_timeout)
        self.reconnect_timeout = None
        try:
            self.sock.shutdown(2)
            self.sock.close()
        except Exception:
            pass
        self.empty_selects = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if self.secure:
            if ssl:
                with open(self.cert_path, 'wb') as cert_fd:
                    cert_fd.write(cert.CA_CERT.encode('utf-8'))
                self.sock = ssl.wrap_socket(self.sock, ca_certs=self.cert_path, cert_reqs=ssl.CERT_REQUIRED)
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
        self.reconnect_delay = self.INITIAL_RECONNECT_DELAY
        self.send_auth()
        if cb:
            cb()

    def _get_from_queue(self):
        while True:
            try:
                yield self.sock_q.get_nowait()
            except Queue.Empty:
                break

    def select(self):
        if not self.sock:
            msg.debug('select(): No socket.')
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


class AgentConnection(BaseAgentConnection):
    MAX_RETRIES = 20
    INITIAL_RECONNECT_DELAY = 500
    Protocol = VimProtocol

    ''' Simple chat server using select '''
    def __init__(self, owner, workspace, on_room_info, get_bufs=True, **kwargs):
        self.username = G.USERNAME
        self.secret = G.SECRET
        self.authed = False
        self.owner = owner
        self.workspace = workspace
        self.on_room_info = on_room_info
        self.get_bufs = get_bufs
        self.workspace_info = {}
        self.bufs_to_stomp = set()
        super(AgentConnection, self).__init__(**kwargs)

    @property
    def workspace_url(self):
        protocol = self.secure and 'https' or 'http'
        return '{protocol}://{host}/r/{owner}/{name}'.format(protocol=protocol, host=self.host, owner=self.owner, name=self.workspace)

    def tick(self):
        self.protocol.push()
        self.select()

    def send_get_buf(self, buf_id, stomp=False):
        self.bufs_to_stomp.add(buf_id)
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
            'room': self.workspace,
            'room_owner': self.owner,
            'client': self.protocol.CLIENT,
            'platform': sys.platform,
            'version': G.__VERSION__,
            'supported_encodings': ['utf8', 'base64'],
        })

    def send_saved(self, buf_id):
        self.put({'name': 'saved', 'id': buf_id})

    def send_msg(self, msg):
        self.put({'name': 'msg', 'data': msg})
        self.protocol.chat(self.username, time.time(), msg, True)

    def on_auth(self):
        self.authed = True
        G.JOINED_WORKSPACE = True
        self.retries = self.MAX_RETRIES
        msg.log('Successfully joined workspace %s/%s' % (self.owner, self.workspace))
        if self.on_room_info:
            self.on_room_info(self)
            self.on_room_info = None

    def is_ready(self):
        return self.authed

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
