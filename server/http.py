#!/app/local/bin/virtual-python
# vim modeline (put ":set modeline" into your ~/.vimrc)
# vim:set expandtab ts=4 sw=4 ai ft=python:
# pylint: disable=superfluous-parens

"""
Endpoints for Polyform API
"""

import time
import traceback
import random
import cherrypy
import polyform
from . import exceptions
from .util import json4store
from .logger import set_DEBUG, log


################################################################################
# random id
def uniqueid():
    """generate a unique id"""
    seed = random.getrandbits(32)
    while True:
        yield "%x" % seed
        seed += 1

###############################################################################
# add object because BaseHTTPRequestHandler is an old style class
class Rest():
    """
    Quick and dirty REST endpoint.  Create a descendant of this class which
    defines a dictionary of endpoints, where each endpoint has a keyword
    and an rx to match for the endpoint on the URI.

    For each keyword define the relative rest_(keyword)_(CRUD) methods,
    where CRUD is one of: Create, Read, Update, Delete
    """

    exposed = True
    json_body = None
    allowed = {}
    reqgen = uniqueid()
    reqid = 0

    ###########################################################################
    #def __init__(self, *args, **kwargs):

    ###########################################################################
    # pylint: disable=no-self-use
    def respond_failure(self, message, status=400):
        """Respond with a failure"""
        if status == 401:
            time.sleep(5) # Future: could add to memcache and increase logarithmically?
        if not message:
            raise exceptions.ServerError("Failure", status)
        raise exceptions.ServerError(message, status)

    ###########################################################################
    # pylint: disable=dangerous-default-value,unused-argument,no-self-use
    def respond(self, content, status=200):
        """Respond with normal content (or not)"""
        if not content:
            cherrypy.response.status = 204
            return None
        cherrypy.response.status = status
        return content

    ###########################################################################
    # pylint: disable=invalid-name,too-many-branches
    def _rest_crud(self, method, *args, **kwargs):
        """Called by the relevant method when content should be posted"""
        #cherrypy.serving.request.reqid =
        self.reqid = next(self.reqgen)
        do_abac_log = False
        if kwargs.get('abac') == "log":
            if set_DEBUG('abac', True):
                do_abac_log = True
        try:
            return getattr(self, method)(*args, **kwargs)
        except exceptions.AuthFailed as err:
            log("authfail", reason=str(err)) # err.args[1])
            cherrypy.response.status = 401
            return {"status": "failed", "message": "Unauthorized"}

        except (ValueError,
                exceptions.InvalidParameter,
                exceptions.ServerError,
                polyform.gql.validate.DataValidationError) as err:
            status = {"status": "failed"}
            cherrypy.response.status = 400
            if type(err) in (list, tuple, exceptions.ServerError): # pylint: disable=unidiomatic-typecheck
                cherrypy.response.status = err.args[1]
                if isinstance(err.args[0], dict):
                    status = err.args[0]
                    status.update({'status': 'failed'}) # pylint: disable=no-member
                else:
                    status['message'] = err.args[0]
            else:
                status['message'] = str(err)
            return status
        except Exception as err:
            log("error", traceback=json4store(traceback.format_exc()))
            raise
        finally:
            if do_abac_log:
                set_DEBUG('abac', False)

    ###########################################################################
    # could decorate these, but .. this is shorter code
    #@cherrypy.tools.accept(media='application/json')
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def POST(self, *args, **kwargs):
        """Wrapper for REST calls"""
        return self._rest_crud('rest_create', *args, **kwargs)

    @cherrypy.tools.json_out()
    def GET(self, *args, **kwargs):
        """Wrapper for REST calls"""
        return self._rest_crud('rest_read', *args, **kwargs)

    #@cherrypy.tools.accept(media='application/json')
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def PUT(self, *args, **kwargs):
        """Wrapper for REST calls"""
        return self._rest_crud('rest_update', *args, **kwargs)

    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def PATCH(self, *args, **kwargs):
        """Wrapper for REST calls""" # not working w/CherryPY and json
        return self._rest_crud('rest_patch', *args, **kwargs)

    @cherrypy.tools.json_out()
    def DELETE(self, *args, **kwargs):
        """Wrapper for REST calls"""
        return self._rest_crud('rest_delete', *args, **kwargs)

    def __call__(self, *args, **kwargs):
        self.respond_failure("Not Found", status=404)

# pylint: disable=too-few-public-methods
class Endpoint():
    """
    Endpoint parent
    """
    server = None

    def __init__(self, server=None, **_kwargs):
        self.server = server

    def housekeeper(self, server):
        """
        Run periodically to do any cleanup, garbage collection, etc
        """

# pylint: disable=wrong-import-position,wrong-import-order
from polyform.sls.reflex_arc import lambda_proxy_auth, AuthFailed

# only works directly on a @cherrypy.expose method
# @cherrypy.tools.register('on_start_resource')
# def authorized(*args, **kwargs):
#     try:
#         lambda_proxy_auth({"headers": self.server.cherry.request.headers}, {})
#     except AuthFailed as err:
#         raise exceptions.AuthFailed(str(err))

def endpoint_authorized(func): # *args, **kwargs):
    """decorator"""
    def authorized_decorator(self, *args, **kwargs):
        """decorator wrapper"""
        lambda_auth(self)
        return func(*args, **kwargs)
    return authorized_decorator

def lambda_auth(master):
    """wrap lambda auth proxy"""
    try:
        return lambda_proxy_auth({"headers": master.server.cherry.request.headers}, {})
    except AuthFailed as err:
        raise exceptions.AuthFailed(str(err))

################################################################################
class Health(Rest, Endpoint):
    """
    Health check
    """
    last_stat = None

    # pylint: disable=unused-argument
    def rest_read(self, *args, **kwargs):
        """Health Check"""

        # check stats -- should be incrementing
        stat = self.server.stat.copy()

        errs = []
        detail = {}
        if kwargs.get('detail') == 'true':
            detail['last-heartbeat'] = 0
            detail['version'] = self.server.conf.deploy_ver

        if stat.heartbeat.last:
            if stat.heartbeat.last + self.server.conf.heartbeat < time.time():
                errs.append("Have not heard a heartbeat")
            if detail:
                detail['last-heartbeat'] = stat.heartbeat.last

        # keep a static copy of the last run stats
        self.last_stat = stat

        # xODO: check db connection health
        if errs:
            return self.respond_failure(detail, status=503)

        return self.respond(detail)
