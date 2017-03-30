from PyQt4 import QtNetwork
from util import logger
import json

class Api(object):
    MAX_PAGE_SIZE = 10000

    def __init__(self, manager):
        self._manager = manager

    def _recvReply(self, reply, cb, error_cb = lambda _: None):
        def _error(text):
            logger.warn(text)
            error_cb(text) # FIXME

        if reply.error() != QtNetwork.QNetworkReply.NoError:
            return _error("API network error! " + reply.errorString())

        attrs = QtNetwork.QNetworkRequest
        status = reply.attribute(attrs.HttpStatusCodeAttribute)
        if status != 200:   # FIXME ?
            return _error("API status error! " + str(status))

        try:
            resp = json.loads(str(reply.readAll()))
        except ValueError:
            return _error("API parse error!")
        return cb(resp)

    # QUrl already escapes query for us, so just concatenate
    @staticmethod
    def _query(endpt, params):
        return endpt + "?" + "&".join(str(key) + "=" + str(params[key]) for key in params)

    def _get(self, endpoint, cb, params = {}):
        req = QtNetwork.QNetworkRequest()
        query = self._query(endpoint, params)
        return self._manager.get(query, req, lambda r: self._recvReply(r, cb))

    def _getPage(self, endpoint, pagesize, pagenum, cb, params = {}):
        params["page[size]"] = pagesize
        params["page[number]"] = pagenum
        return self._get(endpoint, cb, params)

    def _getMany(self, endpoint, count, cb, params = {}):
        def getMore(ret, page, resp):
            data = resp["data"]
            if not isinstance(data, list):
                return
            ret += data
            if data and len(ret) < count:
                self._getPage(endpoint, count, page,
                              lambda r: getMore(ret, page + 1, r), params)
            else:
                cb(ret)

        self._getPage(endpoint, count, 1, lambda r: getMore([], 2, r), params)

    def _getAll(self, endpoint, cb, params = {}):
        return self._getMany(endpoint, self.MAX_PAGE_SIZE, cb, params)

    def _post(self, endpoint, data, cb, err_cb = lambda _: None):
        req = QtNetwork.QNetworkRequest()
        return self._manager.post(endpoint, req, data,
                                  lambda r: self._recvReply(r, cb, err_cb))
