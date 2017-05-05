from oauthlib.oauth2 import LegacyApplicationClient, OAuth2Error, \
    InsecureTransportError, TokenExpiredError
from PyQt4 import QtNetwork
from PyQt4.QtCore import QObject, pyqtSignal, QUrl
import base64
import json
from util import logger


class ApiSettings(object):
    def __init__(self, settings):
        API_P = "api/"
        self.baseUrl = settings.get(API_P + "baseUrl")
        self.clientId = settings.get(API_P + "clientId")
        self.clientSecret = settings.get(API_P + "clientSecret")
        self.accessTokenUri = settings.get(API_P + "accessTokenUri")


class OAuthHandler(object):
    """
    Abstracts away grabbing the OAuth authentication token and adding
    tokens to requests. Uses oauthlib.
    We 'gain' token when we receive a reply from the endpoint. We 'lose' it
    when we find out that it expired when trying to add it.
    """
    def __init__(self, settings):
        self._settings = settings
        self._client = LegacyApplicationClient(self._settings.clientId)
        self._manager = None
        self._hasToken = False

    @property
    def apiManager(self):
        return self._manager

    @apiManager.setter
    def apiManager(self, manager):
        self._manager = manager

    def authorize(self, username, password):
        req = QtNetwork.QNetworkRequest()
        req.setHeader(QtNetwork.QNetworkRequest.ContentTypeHeader,
                      'application/x-www-form-urlencoded')
        req.setRawHeader('Accept', 'application/json')
        h_auth = "Basic " + base64.b64encode(self._settings.clientId + ":" +
                                             self._settings.clientSecret)
        req.setRawHeader('Authorization', h_auth)

        body = self._client.prepare_request_body(
            username=username,
            password=password)
        rep = self._manager.post(QUrl(self._settings.accessTokenUri), req,
                                 body, auth=False)
        rep.finished.connect(self._onAuthorizedResponse)
        rep.error.connect(self._onAuthorizedResponse)
        rep.run()

    def _onAuthorizedResponse(self, reply):
            def _error(text):
                logger.warn(text)
                self._manager.onAuthorizeError()

            if reply.error() != QtNetwork.QNetworkReply.NoError:
                return _error("OAuth network error! " + str(reply.error()))

            try:
                body = json.dumps(reply)    # FIXME
                self._client.parse_request_body_response(body)
            except OAuth2Error:
                return _error("OAuth response parse error!")

            self._hasToken = True
            self._manager.onAuthorized()

    def addToken(self, request, http_method):
        """
        Adds the token to request headers. If the token expired, does not
        modify request.
        """
        url = str(request.url())
        try:
            _, auth_header, _ = self._client.add_token(
                url,
                token_placement='auth_header',
                http_method=http_method)
        except TokenExpiredError:
            # FIXME - this is an oauth quirk, maybe we're better off checking
            # token expiration on our own?
            self._hasToken = False
            raise

        for hname in auth_header:
            request.setRawHeader(hname, auth_header[hname])

    def hasToken(self):
        return self._hasToken


# Api request that can get queued until we get authorized.
class ApiRequest(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal()

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
            self.error.emit()
            return
        self.send_request()

    def on_error(self):
        self._rep.error.disconnect()
        self._rep.finished.disconnect()
        self.error.emit()

    def on_finish(self):
        try:
            resp = json.loads(str(self._rep.readAll()))
        except ValueError:
            self.error.emit()
        self.finished.emit(resp)


class ApiManager(QObject):
    """
    Wraps API HTTP communication - queues requests if we're not authorized yet,
    delegates authorization to OAuthHandler, abstracts host.
    """
    authorized = pyqtSignal()

    def __init__(self, network_manager, settings, oauth):
        QObject.__init__(self)
        self._network_manager = network_manager
        self._settings = settings
        self.oauth = oauth
        self.oauth.apiManager = self
        self._ssl_conf = QtNetwork.QSslConfiguration()
        self._ssl_conf.setProtocol(QtNetwork.QSsl.TlsV1)

    def authorize(self, username, password):
        self.oauth.authorize(username, password)

    def onAuthorized(self):
        self.authorized.emit()

    def is_authorized(self):
        return self.oauth.hasToken()

    def onAuthorizeError(self):     # TODO
        pass

    def _op(self, endpoint, request, httpOp, opName, auth=True):
        request.setUrl(QUrl(self._settings.baseUrl).resolved(endpoint))
        request.setSslConfiguration(self._ssl_conf)

        return ApiRequest(self, request, httpOp, opName, auth)

    def get(self, endpoint, request, auth=True):
        return self._op(endpoint, request, self._network_manager.get, "GET",
                        auth)

    def post(self, endpoint, request, data, auth=True):
        return self._op(endpoint, request,
                        lambda r: self._network_manager.post(r, data), "POST",
                        auth)

    def put(self, endpoint, request, data, auth=True):
        return self._op(endpoint, request,
                        lambda r: self._network_manager.put(r, data), "PUT",
                        auth)

# FIXME - turn everything below into unit tests

from PyQt4.QtGui import QApplication
import sys
import api


class MockSettings(object):
    def __init__(self):
        self.baseUrl = 'http://localhost:8010'
        self.accessTokenUri = '/oauth/token'
        self.clientId = 'faf-client'
        self.clientSecret = 'banana'


LOGIN = "test"
PASSWORD = "test_password"


def doTest(body):
    print("Received!")
    print(body)
    sys.exit(0)


def testLogin():
    a = QApplication([])
    settings = MockSettings()
    oauth = OAuthHandler(settings)
    am = QtNetwork.QNetworkAccessManager()
    manager = ApiManager(am, settings, oauth)
    manager.authorize(LOGIN, PASSWORD)
    faf_api = api.Api(manager)
    req = faf_api._getAll("/data/featuredMod")
    req.finished.connect(doTest)
    req.run()
    a.exec_()

if __name__ == "__main__":
    testLogin()
