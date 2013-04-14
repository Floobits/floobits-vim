import os
import json
import socket
import Queue
import select
import collections

ssl = False
try:
    import ssl
except ImportError:
    pass

import msg
import sublime
import shared as G


SOCKET_Q = Queue.Queue()

CERT = os.path.join(os.getcwd(), 'startssl-ca.pem')
print("CERT is ", CERT)


class AgentConnection(object):
    ''' Simple chat server using select '''
    def __init__(self, owner, room, host=None, port=None, secure=True, on_connect=None):
        self.sock = None
        self.buf = ''
        self.reconnect_delay = G.INITIAL_RECONNECT_DELAY
        self.username = G.USERNAME
        self.secret = G.SECRET
        self.authed = False
        self.host = host or G.DEFAULT_HOST
        self.port = port or G.DEFAULT_PORT
        self.secure = secure
        self.owner = owner
        self.room = room
        self.retries = G.MAX_RETRIES
        self.on_connect = on_connect
        self.chat_deck = collections.deque(maxlen=10)
        self.empty_selects = 0
        self.room_info = {}

    def stop(self):
        msg.log('Disconnecting from room %s/%s' % (self.owner, self.room))
        try:
            self.retries = -1
            self.sock.shutdown(2)
            self.sock.close()
        except Exception:
            pass
        msg.log('Disconnected.')

    # def send_msg(self, msg):
    #     self.put(json.dumps({'name': 'msg', 'data': msg}))
    #     self.chat(self.username, time.time(), msg, True)

    def is_ready(self):
        return self.authed

    @staticmethod
    def put(item):
        #TODO: move json_dumps here
        if not item:
            return
        SOCKET_Q.put(item + '\n')
        qsize = SOCKET_Q.qsize()
        if qsize > 0:
            msg.debug('%s items in q' % qsize)

    def reconnect(self):
        try:
            self.sock.close()
        except Exception:
            pass
        G.CONNECTED = False
        self.room_info = {}
        self.buf = ''
        self.sock = None
        self.authed = False
        self.reconnect_delay *= 1.5
        if self.reconnect_delay > 10000:
            self.reconnect_delay = 10000
        if self.retries > 0:
            msg.log('Floobits: Reconnecting in %sms' % self.reconnect_delay)
            sublime.set_timeout(self.connect, int(self.reconnect_delay))
        elif self.retries == 0:
            sublime.error_message('Floobits Error! Too many reconnect failures. Giving up.')
        self.retries -= 1

    def connect(self):
        self.empty_selects = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if self.secure:
            if ssl:  # ST2 on linux doesn't have the ssl module. Not sure about windows
                self.sock = ssl.wrap_socket(self.sock, ca_certs=CERT, cert_reqs=ssl.CERT_REQUIRED)
            else:
                msg.log('No SSL module found. Connection will not be encrypted.')
                if self.port == G.DEFAULT_PORT:
                    self.port = 3148  # plaintext port
        msg.log('Connecting to %s:%s' % (self.host, self.port))
        try:
            print self.host, self.port
            self.sock.connect((self.host, self.port))
            if self.secure and ssl:
                self.sock.do_handshake()
        except socket.error as e:
            msg.error('Error connecting:', e)
            self.reconnect()
            return
        self.sock.setblocking(0)
        msg.log('Connected!')
        self.reconnect_delay = G.INITIAL_RECONNECT_DELAY
        sublime.set_timeout(self.select, 0)
        self.auth()

    def auth(self):
        global SOCKET_Q
        # TODO: we shouldn't throw away all of this
        SOCKET_Q = Queue.Queue()
        self.put(json.dumps({
            'username': self.username,
            'secret': self.secret,
            'room': self.room,
            'room_owner': self.owner,
            'version': G.__VERSION__
        }))

    def get_patches(self):
        while True:
            try:
                yield SOCKET_Q.get_nowait()
            except Queue.Empty:
                break

    def protocol(self, req):
        self.buf += req
        while True:
            before, sep, after = self.buf.partition('\n')
            if not sep:
                break
            try:
                data = json.loads(before)
            except Exception as e:
                print('Unable to parse json:', e)
                print('Data:', before)
                raise e
            G.proto.handle(data)
            self.buf = after

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
                self.protocol(buf)
            else:
                self.empty_selects += 1
                if self.empty_selects > 10:
                    msg.error('No data from sock.recv() {0} times.'.format(self.empty_selects))
                    return self.reconnect()

        if _out:
            for p in self.get_patches():
                if p is None:
                    SOCKET_Q.task_done()
                    continue
                try:
                    msg.debug('writing patch: %s' % p)
                    self.sock.sendall(p)
                    SOCKET_Q.task_done()
                except Exception as e:
                    msg.error('Couldn\'t write to socket: %s' % str(e))
                    return self.reconnect()

        #TODO: this double calls in vim
        sublime.set_timeout(self.select, 100)
