"""
Handler Polyforms
"""

import os
import sys
import re
import importlib
import json
import cherrypy
from dictlib import Dict
from .. import exceptions
from ..http import Endpoint, Rest, lambda_auth

POLYS = dict()

# pylint: disable=too-many-locals
def initialize():
    """module initialization--cache some things"""
    base = "./polys"
    # just sugar
    def pjoin(*args):
        return os.path.join(*args)

    cwd = os.getcwd()
    polys = list()
    for pname in os.listdir(base):
        if os.path.isdir(pjoin(base, pname)):
            print("FOUND polyform " + pname)
            for fname in os.listdir(pjoin(base, pname)):
                if os.path.isdir(pjoin(base, pname, fname)):
                    print("      facet " + pname + "." + fname)
                    polys.append(Dict(
                        path=pjoin(base, pname, fname),
                        name=pname + "." + fname
                    ))

    for poly in polys:
        pname, fname = poly.name.split(".")
        bpath = pjoin(cwd, poly.path)
        path = pjoin(bpath, "_polyform.json")
        with open(path) as conf:
            pconf = json.load(conf)

        os.chdir(pjoin(cwd, poly.path))
        sys.path.append('.')
        form = pconf['forms'][pconf['target']]
        run = re.sub(r'[^a-z0-9_.]+', '', form['run'])
        modexp = run.split(".")
        modpath = ".".join(modexp[0:-1])
        importlib.invalidate_caches()
        mod = importlib.import_module(modpath)
        sys.path = sys.path[:-1]
        os.chdir(cwd)

        POLYS[poly.name] = Dict(conf=pconf, mod=mod, path=bpath, run=modexp[-1])

initialize()

# TODO: actually key this off of the config polyform.forms[form].run
class Handler(Endpoint, Rest):
    """docstring"""

    def rest_read(self, facet_path, *_args, **_kwargs):
        """read"""
        raise ValueError("HTTP GET is not a supported method")

    def rest_create(self, facet_path, *_args, **_kwargs):
        """call a polyform"""
        lambda_auth(self) # update so claims has polyform name in it

        facet = POLYS.get(facet_path)
        if not facet:
            print("Cannot find polyform facet: {}, polyform: {}".format(facet_path, POLYS))
            raise exceptions.InvalidParameter("Cannot find polyform facet: {}".format(facet_path))

        os.chdir(facet.path)

        result = getattr(facet.mod, facet.run)(
            dict(headers={}, parsed_body=cherrypy.request.json),
            {}
        )
        if not result.get('status'):
            result['status'] = "success"
        return result
