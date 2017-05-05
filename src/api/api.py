from PyQt4 import QtNetwork
from PyQt4.QtCore import QObject, pyqtSignal, QUrl


class ApiListRequest(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal()

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
        if not values:
            self.finished.emit(self._result)
            return
        if not isinstance(values, list):
            self.at_error()
            return

        if len(self._result) + len(values) >= self._count:
            values = values[:self._count - len(self._result)]

        self._result += values
        if len(self._result) >= self._count:
            self.finished.emit(self._result)
            return
        self._run_next_req()

    def _at_error(self):
        self._nextreq = None
        self.error.emit()


class Api(object):
    MAX_PAGE_SIZE = 10000

    def __init__(self, manager):
        self._manager = manager

    def _query(self, endpt, params):
        url = QUrl(endpt)
        for key in params:
            url.addQueryItem(key, str(params[key]))
        return url

    def _get(self, endpoint, params={}):
        req = QtNetwork.QNetworkRequest()
        query = self._query(endpoint, params)
        return self._manager.get(query, req)

    def _getPage(self, endpoint, pagesize, pagenum, params={}):
        params["page[size]"] = pagesize
        params["page[number]"] = pagenum
        return self._get(endpoint, params)

    def _getMany(self, endpoint, count, params={}):
        def getReqs():
            for i in range(1, count + 1):
                yield self._getPage(QUrl(endpoint), count, i, params)
        return ApiListRequest(getReqs(), count)

    def _getAll(self, endpoint, params={}):
        return self._getMany(endpoint, self.MAX_PAGE_SIZE, params)

    def _post(self, endpoint, data):
        req = QtNetwork.QNetworkRequest()
        return self._manager.post(QUrl(endpoint), req, data)
