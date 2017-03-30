import urllib.parse
from PyQt4 import QtNetwork
from util import logger
import json

class Api(object):
    MAX_PAGE_SIZE = 10000

    def __init__(self, manager):
        self._manager = manager

    def _recvReply(self, reply, cb, error_cb = lambda _: pass):
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

    def _get(self, endpoint, params, cb):
        req = QtNetwork.QNetworkRequest()
        paramstr = urllib.parse.urlencode(params)
        newept = endpoint + "?" + paramstr
        return self._manager.get(newept, req, lambda r: self._recvReply(r, cb))

    def _getPage(self, endpoint, pagesize, pagenum, params, cb):
        params["page[size]"] = pagesize
        params["page[number]"] = pagenum
        return self._get(endpoint, params, cb)

    def _getMany(self, endpoint, count, params, cb):
        ret = []
        page = 1
        def getMore(resp):
            if not isinstance(resp, list):
                return
            ret += resp
            if resp and len(ret) < count:
                page += 1
                self._getPage(endpoint, count, page, params, getMore)
            else:
                cb(ret)

        self._getPage(endpoint, count, page, params, getMore)

    def _getAll(self, endpoint, params, cb):
        return self._getMany(self, endpoint, MAX_PAGE_SIZE, params, cb)

    def _post(self, endpoint, data, cb, err_cb):
        req = QtNetwork.QNetworkRequest()
        return self._manager.post(endpoint, req, data,
                                  lambda r: self._recvReply(r, cb, err_cb))
