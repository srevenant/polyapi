#!/usr/bin/env python3
# not: /app/local/bin/virtual-python
# vim modeline (put ":set modeline" into your ~/.vimrc)
# vim:set expandtab ts=4 sw=4 ai ft=python:
# pylint: disable=superfluous-parens

"""
General Webhooks and simple API routing
"""

import os
import sys
import time
import logging
import logging.config
import traceback
import cherrypy._cplogging
from . import SERVER

################################################################################
# pylint: disable=protected-access
class CherryLog(cherrypy._cplogging.LogManager):
    """
    Because CherryPy logging and python logging are a hot mess.  Modern bitdata
    systems and 12-factor apps want key value logs for ease of use.  This gives
    us an easy switch by using Poly's logging
    """

    ############################################################################
    def time(self):
        """do not want"""
        return ''

    ############################################################################
    # pylint: disable=redefined-outer-name
    def error(self, msg='', context='', severity=logging.INFO, traceback=False):
        """log error"""

        kwargs = {}
        if traceback:
            # pylint: disable=protected-access
            kwargs['traceback'] = cherrypy._cperror.format_exc()
            if not msg:
                msg = "error"

        if isinstance(msg, bytes):
            msg = msg.decode()

        log(error=msg, type="error", context=context, severity=severity, **kwargs)

    ############################################################################
    def access(self):
        """log access"""
        request = cherrypy.serving.request
        remote = request.remote
        response = cherrypy.serving.response
        outheaders = response.headers
        inheaders = request.headers
        if response.output_status is None:
            status = "-"
        else:
            status = response.output_status.split(" ".encode(), 1)[0]

        remaddr = inheaders.get('X-Forwarded-For', None) or \
                  remote.name or remote.ip

        if isinstance(status, bytes):
            status = status.decode()

        # this is set in abac.py
        login = cherrypy.serving.request.login
        kwargs = dict()
        if login and login.token_name:
            kwargs['token'] = login.token_name
            # Notes: insert other auth attributes?

        log("type=http status=" + str(status),
            query=request.request_line,
            remote=remaddr,
            len=outheaders.get('Content-Length', '') or '-',
            **kwargs)

################################################################################
class Logger(logging.StreamHandler):
    """
    A handler class which allows the cursor to stay on
    one line for selected messages
    """
    on_same_line = False

    ############################################################################
    def configure(self, *args):
        """do not want"""

    ############################################################################
    def emit(self, record):
        """Overriding emit"""
        try:
            msg = record.msg.strip()
            log(msg)
        except (KeyboardInterrupt, SystemExit):
            raise
        except: # pylint: disable=bare-except
            self.handleError(record)

    ############################################################################
    # pylint: disable=redefined-builtin
    def format(self, record):
        return record.msg.decode()

###############################################################################
# pylint: disable=no-self-use
def trace(arg):
    """Trace log debug info"""

    with open("trace", "at") as outf:
        outf.write("[{}] {} {}\n".format(os.getpid(), time.time(), arg))

###############################################################################
def set_DEBUG(module, value): # pylint: disable=invalid-name
    """do_DEBUG() wrapper from rfx.Base object, pivoting off SERVER global"""
    if SERVER:
        if not value:
            del SERVER.debug[module]
            return True
        if SERVER.debug.get(module, None) is None:
            SERVER.debug[module] = value
            return True
    return False

###############################################################################
def do_DEBUG(*module): # pylint: disable=invalid-name
    """do_DEBUG() wrapper from rfx.Base object, pivoting off SERVER global"""
    if SERVER:
        return SERVER.do_DEBUG(*module)
    return False

def debug(*args, **kwargs):
    """
    debug wrapper for logging
    """
    try:
        if SERVER:
            SERVER.DEBUG(*args, **kwargs)
        else:
            print("{} {}".format(args, kwargs))
    except Exception: # pylint: disable=broad-except
        with open("log_failed", "ta") as out:
            out.write("\n\n--------------------------------------------------\n\n")
            traceback.print_exc(file=out)
            out.write(str(args))
            out.write(str(kwargs))

###############################################################################
def log(*args, **kwargs):
    """
    Log key=value pairs for easier splunk processing

    test borked
    x>> log(test="this is a test", x='this') # doctest: +ELLIPSIS
    - - [...] test='this is a test' x=this
    """
    try:
        if SERVER:
            try:
                if SERVER.conf.get('requestid'):
                    # note: danger: this should be injected by traffic management,
                    # enable it with config requestid=true
                    reqid = SERVER.cherry.request.headers.get('X-Request-Id')
                    if reqid:
                        kwargs['reqid'] = reqid
                    elif SERVER.cherry.serving.request.__dict__.get('reqid'):
                        kwargs['reqid'] = SERVER.cherry.serving.request.reqid
                elif SERVER.cherry.serving.request.__dict__.get('reqid'):
                    kwargs['reqid'] = SERVER.cherry.serving.request.reqid

            except: # pylint: disable=bare-except
                SERVER.NOTIFY("Logging ServerError: " + traceback.format_exc())
            SERVER.NOTIFY(*args, **kwargs)
        else:
            sys.stdout.write(" ".join(args) + " ")
            for key, value in kwargs.items():
                sys.stdout.write("{}={} ".format(key, value))
            sys.stdout.write("\n")
            sys.stdout.flush()
    except Exception: # pylint: disable=broad-except
        with open("log_failed", "ta") as out:
            out.write("\n\n--------------------------------------------------\n\n")
            traceback.print_exc(file=out)
            out.write(str(args))
            out.write(str(kwargs))

def abort(*msg):
    """
    log and exit(1)
    """
    log(*msg)
    sys.exit(1)
