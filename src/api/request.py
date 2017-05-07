from PyQt4.QtCore import QObject, pyqtSignal
from oauthlib.oauth2 import InsecureTransportError, TokenExpiredError
import json


# Api request that can get queued until we get authorized.
class ApiRequest(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, manager, request, http_op, opname, auth):
        QObject.__init__(self)
        self._manager = manager
        self._req = request
        self._op = http_op
        self._opname = opname
        self._rep = None
        self._auth = auth

    def run(self):
        if not self._auth or self._manager.is_authorized():
            self.send_request()
        else:
            self._manager.authorized.connect(self.at_auth)

    def send_request(self):
        self._rep = self._op(self._req)
        self._rep.error.connect(self.on_error)
        self._rep.finished.connect(self.on_finish)

    def at_auth(self):
        self._manager.authorized.disconnect(self.at_auth)
        try:
            self._manager.oauth.addToken(self._req, self._opname)
        except (TokenExpiredError, InsecureTransportError):
            self.error.emit("Oauth expiry / transport error")
            return
        self.send_request()

    def on_error(self, error):
        self._rep.error.disconnect()
        self._rep.finished.disconnect()
        data = str(self._rep.readAll())
        self.error.emit("Reply error {}: {}".format(error, data))

    def on_finish(self):
        try:
            data = str(self._rep.readAll())
            resp = json.loads(data)
        except ValueError:
            self.error.emit("Failed to parse json: " + data)
        self.finished.emit(resp)


class ApiListRequest(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, requests, count):
        QObject.__init__(self)
        self._reqs = requests
        self._nextreq = None
        self._result = []
        self._count = count

    def run(self):
        self._run_next_req()

    def _run_next_req(self):
        try:
            self._nextreq = next(self._reqs)
        except StopIteration:
            self.finished.emit(self._result)
            return
        self._nextreq.finished.connect(self._at_finished)
        self._nextreq.error.connect(self._at_error)
        self._nextreq.run()

    def _at_finished(self, values):
        if not isinstance(values, dict) or "data" not in values:
            self._at_error("Expected a dict response with data")
            return
        items = values["data"]

        if not isinstance(items, list):
            self._at_error("Data is not a list")
            return

        if len(items) == 0:
            self.finished.emit(self._result)
            return

        if len(self._result) + len(items) >= self._count:
            items = items[:self._count - len(self._result)]

        self._result += items
        if len(self._result) >= self._count:
            self.finished.emit(self._result)
            return
        self._run_next_req()

    def _at_error(self, text):
        self._nextreq = None
        self.error.emit(text)
