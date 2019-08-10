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
import base64
import logging
import logging.config
import traceback
import argparse
import resource
import threading
import cherrypy._cplogging
import setproctitle
import timeinterval
import dictlib
from dictlib import Dict
from server.util import json2data
from server import http, SERVER, logger

################################################################################
class Server():
    """
    central server
    """
    conf = None
    #dbm = None
    stat = dictlib.Obj(heartbeat=dictlib.Obj(count=0, last=0),
                       #dbm=dictlib.Obj(count=0),
                       next_report=0, last_rusage=None)
    mgr = None
    cherry = None
    endpoints = None
    endpoint_conf = None
    endpoint_names = None

    def __init__(self): #, *_args, **_kwargs):
        self.cherry = cherrypy
        self.conf = dict()
        self.endpoint_conf = {
            '/': {
                'response.headers.server': "stack",
                'tools.secureheaders.on': True,
                'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
                'request.method_with_bodies': ('PUT', 'POST', 'PATCH'),
            }
        }

        self.endpoints = list()
        self.endpoint_names = list()

        print(__file__)
        ## Eventually make this read from __file__ or other globals to get plugin path
#        for fname in os.listdir('endpoints'):
#            if not os.path.isfile(os.path.join('endpoints', fname)):
#                continue
#            if not re.search(r'^[a-z0-9]+.py$', fname):
#                print("skip " + fname)
#                continue
#            endpoint = re.sub(r'\.py$', '', fname)
#            self.endpoint_names.append(endpoint)

    def monitor(self):
        """
        internal heartbeat from Cherrypy.process.plugins.Monitor
        """
        self.stat.heartbeat.last = time.time()

        #alive = 0
        #dead = 0

        if self.stat.next_report < self.stat.heartbeat.last:
            logger.log("type=status-report", **self.status_report())

    def status_report(self):
        """report on internal usage"""

        cur = resource.getrusage(resource.RUSAGE_SELF)
        last = self.stat.last_rusage
        if not last:
            last = cur
        report = {
            "utime":round(cur.ru_utime - last.ru_utime, 2),
            "stime":round(cur.ru_stime - last.ru_stime, 2),
            "minflt":round(cur.ru_minflt - last.ru_minflt, 2),
            "majflt":round(cur.ru_majflt - last.ru_majflt, 2),
            "nswap":round(cur.ru_nswap - last.ru_nswap, 2),
            "iblk":round(cur.ru_inblock - last.ru_inblock, 2),
            "oblk":round(cur.ru_oublock - last.ru_oublock, 2),
            "msgsnd":round(cur.ru_msgsnd - last.ru_msgsnd, 2),
            "msgrcv":round(cur.ru_msgrcv - last.ru_msgrcv, 2),
            "nvcsw":round(cur.ru_nvcsw - last.ru_nvcsw, 2),
            "nivcsw":round(cur.ru_nivcsw - last.ru_nivcsw, 2),
            "maxrss":round((cur.ru_maxrss-last.ru_maxrss)/1024, 2),
            "ixrss":round((cur.ru_ixrss-last.ru_ixrss)/1024, 2),
            "idrss":round((cur.ru_idrss-last.ru_idrss)/1024, 2),
            "isrss":round((cur.ru_isrss-last.ru_isrss)/1024, 2),
            "threads":threading.active_count()
        }

        self.stat.last_rusage = cur
        self.stat.next_report = self.stat.heartbeat.last + self.conf['status_report']

        return report

    def add_endpoint(self, endpoint, mod):
        """add an endpoint as a pluggable module"""
        # pylint: disable=no-member
        route = self.conf.server.route_base + "/" + mod.__name__.split(".")[-1]
        print("route=" + route)
        handler = mod.Handler(server=self, route=route)
        print("handler={}".format(handler))
        cherrypy.tree.mount(handler, route, self.endpoint_conf)
        self.endpoints.append(Dict(name=endpoint, mod=mod, handler=handler, route=route))

    # pylint: disable=too-many-locals,too-many-statements
    def start(self, test=True):
        """
        Startup script for webhook routing.
        Called from agent start
        """

        cherrypy.log = logger.CherryLog()
        cherrypy.config.update({
            'log.screen': False,
            'log.access_file': '',
            'log.error_file': ''
        })
        cherrypy.engine.unsubscribe('graceful', cherrypy.log.reopen_files)
        logging.config.dictConfig({
            'version': 1,
            'formatters': {
                'custom': {
                    '()': 'server.logger.Logger'
                }
            },
            'handlers': {
                'console': {
                    'level':'INFO',
                    'class': 'server.logger.Logger',
                    'formatter': 'custom',
                    'stream': 'ext://sys.stdout'
                }
            },
            'loggers': {
                '': {
                    'handlers': ['console'],
                    'level': 'INFO'
                },
                'cherrypy.access': {
                    'handlers': ['console'],
                    'level': 'INFO',
                    'propagate': False
                },
                'cherrypy.error': {
                    'handlers': ['console'],
                    'level': 'INFO',
                    'propagate': False
                },
            }
        })

        defaults = {
            'deploy_ver': 0, # usable for deployment tools
            'server': {
                'route_base': '/api/v1',
                'port': 64000,
                'host': '0.0.0.0'
            },
            'heartbeat': 10,
            'status_report': 3600, # every hour
            'requestid': True,
            'refresh_maps': 300,
            'cache': {
                'housekeeper': 60,
                'policies': 300,
                'sessions': 300,
                'groups': 300
            },
            'crypto': {
# pylint: disable=bad-continuation
#                '000': {
# dd if=/dev...
#                    'key': "",
#                    'default': True,
#                }
            },
            'db': {
                'database': 'reflex_engine',
                'user': 'root'
            },
            'auth': {
                'expires': 300
            }
        }

        cfgin = None

        # try docker secrets
        if os.path.exists("/run/secrets/SERVER_CONFIG"):
            with open("/run/secrets/SERVER_CONFIG") as infile:
                cfgin = infile.read()

        # try environ
        if not cfgin:
            cfgin = os.environ.get('SERVER_CONFIG')

        if cfgin:
            try:
                cfgin = json2data(base64.b64decode(cfgin))
            except: # pylint: disable=bare-except
                try:
                    cfgin = json2data(cfgin)
                except Exception as err: # pylint: disable=broad-except
                    traceback.print_exc()
                    logger.abort("Cannot process SERVER_CONFIG: " + str(err) + " from " + cfgin)

            conf = Dict(dictlib.union(defaults, cfgin))
        else:
            logger.log("Unable to find configuration, using defaults!")
            conf = Dict(defaults)

        # cherry py global
        cherry_conf = {
            'server.socket_port': 64000,
            'server.socket_host': '0.0.0.0'
        }

        if dictlib.dig_get(conf, 'server.port'): # .get('port'):
            cherry_conf['server.socket_port'] = int(conf.server.port)
        if dictlib.dig_get(conf, 'server.host'): # .get('host'):
            cherry_conf['server.socket_host'] = conf.server.host

        # if production mode
        if test:
            logger.log("Test mode enabled", type="notice")
            conf['test_mode'] = True
        else:
            cherry_conf['environment'] = 'production'
            conf['test_mode'] = False

        sys.stdout.flush()
        cherrypy.config.update(cherry_conf)
        cherrypy.config.update({'engine.autoreload.on': False})
        self.conf = conf

        # eventually
#        for mod in self.endpoint_names:
#            self.add_endpoint(mod)

        # hack for now
        from server.endpoints import polyform
        self.add_endpoint('polyform', polyform)

        # startup cleaning interval
        def housekeeper(server):
            for endpoint in server.endpoints:
                try:
                    endpoint.handler.housekeeper(server)
                except: # pylint: disable=bare-except
                    traceback.print_exc()
        timeinterval.start(conf.auth.expires * 1000, housekeeper, self)

        # mount routes
        cherrypy.tree.mount(http.Health(server=self),
                            conf.server.route_base + "/health",
                            self.endpoint_conf)

        int_mon = cherrypy.process.plugins.Monitor(cherrypy.engine,
                                                   self.monitor,
                                                   frequency=conf.heartbeat/2)
        int_mon.start()

        # whew, now start the server
        logger.log("Base path={}".format(conf.server.route_base), type="notice")
        cherrypy.engine.start()
        cherrypy.engine.block()

################################################################################
def main():
    """startup a server"""
    global SERVER # pylint: disable=global-statement
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action='append')
    parser.add_argument("--test", action='store_true')

    args = parser.parse_args()

#    base = rfx.Base(debug=args.debug, logfmt='txt').cfg_load()
#    if args.test:
#        base.timestamp = False
#    else:
#        base.timestamp = True
    setproctitle.setproctitle('polyapi') # pylint: disable=no-member,c-extension-no-member

    SERVER = Server()
    SERVER.start(test=args.test)

################################################################################
if __name__ == "__main__":
    main()
