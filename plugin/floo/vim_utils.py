
try:
    unicode()
except NameError:
    unicode = str

try:
    from .common import shared as G
    assert G
except (ImportError, ValueError):
    from common import shared as G


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
