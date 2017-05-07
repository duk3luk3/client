from oauthlib.oauth2 import LegacyApplicationClient, OAuth2Error, \
    TokenExpiredError
from PyQt4 import QtNetwork
from PyQt4.QtCore import QObject, pyqtSignal, QUrl
import base64
import json
from request import ApiRequest


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
        self._rep = None

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
        self._rep = self._manager.post(QUrl(self._settings.accessTokenUri),
                                       req, body, auth=False)
        self._rep.finished.connect(self._onAuthorizedResponse)
        self._rep.error.connect(self._onError)
        self._rep.run()

    def _onError(self):
        self._rep = None
        self._manager.onAuthorizeError()

    def _onAuthorizedResponse(self, reply):
        self._rep = None
        try:
            body = json.dumps(reply)    # FIXME
            self._client.parse_request_body_response(body)
        except OAuth2Error:
            return self._onError()

        self._hasToken = True
        self._manager.onAuthorized()

    def addToken(self, request, http_method):
        """
        Adds the token to request headers. If the token expired, does not
        modify request.
        """
        url = str(request.url().toString())
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
        self.baseUrl = 'https://api.dev.faforever.com'
        self.accessTokenUri = '/oauth/token'
        self.clientId = '3bc8282c-7730-11e5-8bcf-feff819cdc9f'
        self.clientSecret = '6035bd78-7730-11e5-8bcf-feff819cdc9f'


LOGIN = "YourLogin"
PASSWORD = "YourPassword"


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
