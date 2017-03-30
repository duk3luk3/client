from oauthlib.oauth2 import LegacyApplicationClient, OAuth2Error, \
                            InsecureTransportError, TokenExpiredError
from PyQt4 import QtNetwork
from PyQt4.QtCore import QUrl
import base64
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
        self._manager.post(self._settings.accessTokenUri, req, body,
                           self._onAuthorizedResponse, auth = False)

    def _onAuthorizedResponse(self, reply):
            def _error(text):
                logger.warn(text)
                self._manager.onAuthorizeError()

            if reply.error() != QtNetwork.QNetworkReply.NoError:
                return _error("OAuth network error! " + str(reply.error()))
            
            attrs = QtNetwork.QNetworkRequest
            status = reply.attribute(attrs.HttpStatusCodeAttribute)
            if status != 200:   # FIXME ?
                return _error("OAuth status error! " + str(status))

            try:
                body = str(reply.readAll())
                params = self._client.parse_request_body_response(body)
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
            _, auth_header, _ = self._client.add_token(url,
                                               token_placement='auth_header',
                                               http_method = http_method)
        except TokenExpiredError:
            # FIXME - this is an oauth quirk, maybe we're better off checking
            # token expiration on our own?
            self._hasToken = False
            raise

        for hname in auth_header:
            request.setRawHeader(hname, auth_header[hname])

    def hasToken(self):
        return self._hasToken


class RequestQueue(object):
    """
    Simple queue for delaying function calls. You queue functions that return
    a bool telling if they should be re-queued. readyfn returns whether the
    queue should continue being processed and is falled before processing
    each item in the queue.
    """
    def __init__(self, readyfn):  
        self.isReady = readyfn
        self._queue = []

    def process(self):
        while self.isReady() and self._queue:
            fn = self._queue.pop(0)
            if fn():
                self._queue.append(fn)

    def append(self, fn):
        self._queue.append(fn)
        self.process()


class ApiManager(object):
    """
    Wraps API HTTP communication - queues requests if we're not authorized yet,
    delegates authorization to OAuthHandler, abstracts host.
    """
    def __init__(self, network_manager, settings, oauth):
        self._network_manager = network_manager
        self._settings = settings
        self._oauth = oauth
        self._oauth.apiManager = self
        self._ssl_conf = QtNetwork.QSslConfiguration()
        self._ssl_conf.setProtocol(QtNetwork.QSsl.TlsV1)
        self._op_queue = RequestQueue(self._oauth.hasToken)

    def authorize(self, username, password):
        self._oauth.authorize(username, password)

    def onAuthorized(self):
        self._op_queue.process()

    def onAuthorizeError(self): # TODO
        pass

    def _op(self, endpoint, request, cb, httpOp, opName, auth = True):
        """
        Queue a HTTP operation, calling cb with reply if it finishes.
        If auth is true, queue the operation until we have the token.
        """
        request.setUrl(QUrl(self._settings.baseUrl + endpoint))
        request.setSslConfiguration(self._ssl_conf)

        def send_request():
            reply = httpOp(request)
            reply.finished.connect(lambda: cb(reply))

        def queued_auth_request():
            try:
                self._oauth.addToken(request, opName)
            except TokenExpiredError:
                return True     # requeue
            except InsecureTransportError:
                return False    # FIXME - don't fail silently?
            send_request()

        if not auth:
            send_request()
        else:
            self._op_queue.append(queued_auth_request)

    def get(self, endpoint, request, cb, auth = True):
        return self._op(endpoint, request, cb, self._network_manager.get, "GET",
                        auth)
    
    def post(self, endpoint, request, data, cb, auth = True):
        return self._op(endpoint, request, cb,
                        lambda r: self._network_manager.post(r, data), "POST",
                        auth)
    
    def put(self, endpoint, request, data, cb, auth = True):
        return self._op(endpoint, request, cb,
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


LOGIN="test"
PASSWORD="test_password"

def doTest(body):
    print "Received!"
    print body
    sys.exit(0)

def testLogin():
    a = QApplication([])
    settings = MockSettings()
    oauth = OAuthHandler(settings)
    am = QtNetwork.QNetworkAccessManager()
    manager = ApiManager(am, settings, oauth)
    manager.authorize(LOGIN, PASSWORD)
    faf_api = api.Api(manager)
    faf_api._getAll("/data/featuredMod", doTest)
    a.exec_()

if __name__ == "__main__":
    testLogin()
