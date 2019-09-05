#$#HEADER-START
# vim:set expandtab ts=4 sw=4 ai ft=python:
#
#     Reflex Configuration Event Engine
#
#     Copyright (C) 2016 Brandon Gillespie
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU Affero General Public License as published
#     by the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU Affero General Public License for more details.
#
#     You should have received a copy of the GNU Affero General Public License
#     along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#$#HEADER-END

"""
boilerplate for CherryPy bits.
plus basic REST handlers.
"""

import base64
import re
import json
import cherrypy
from . import exceptions

################################################################################
def secureheaders():
    """Establish secure headers"""
    headers = cherrypy.response.headers
    headers['X-Frame-Options'] = 'DENY'
    headers['X-XSS-Protection'] = '1; mode=block'
    headers['Content-Security-Policy'] = "default-src='self'"

cherrypy.tools.secureheaders = cherrypy.Tool('before_finalize', secureheaders, priority=60)

###############################################################################
RX_TOK = re.compile(r'[^a-z0-9-]')
def get_jti(in_jwt):
    """
    Pull the JTI from the payload of the jwt without verifying signature.
    Dangerous, not good unless secondary verification matches.
    """
    payload_raw = in_jwt.split(".")[1]

    missing_padding = 4 - len(payload_raw) % 4
    if missing_padding:
        payload_raw += '=' * missing_padding
    try:
        data = json2data(base64.b64decode(payload_raw))
    except:
        raise ValueError("Error decoding JWT: {}".format(in_jwt))

    token_id = str(data.get('jti', ''))
    if RX_TOK.search(token_id):
        raise ValueError("Invalid User ID: {}".format(token_id))

    return token_id

################################################################
def json4human(data):
    """Json output for humans"""
    return json.dumps(data, indent=2, sort_keys=True)

def json4store(data, **kwargs):
    """Json output for storage"""
    return json.dumps(data, **kwargs)

def json2data(string):
    """json to its python representation"""
    return json.loads(string)

################################################################################
def get_json_body():
    """Helper to get JSON content"""
    try:
        body = cherrypy.request.json
    except AttributeError:
        try:
            body = cherrypy.request.body.read()
        except TypeError:
            raise exceptions.ServerError("Unable to load JSON content", 400)

    if isinstance(body, str): # or isinstance(body, unicode):
        return json2data(body)
    return body
