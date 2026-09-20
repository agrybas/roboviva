# -*- coding: utf-8 -*-
"""Scripted replacement for urllib2.urlopen, for the legacy fetch functions.

The seam that makes RideWithGPS behavior testable. A *script* is an ordered
list of what the server does on each successive call:

    [{"status": 200, "headers": {"ETag": "W/\\"abc\\""}, "body": "{...}"},
     {"raise": "timeout"},
     {"raise": "http", "status": 404}]

The stub also records every request -- full URL and headers -- so the goldens
can pin things the return value alone would not show, notably the literal
`api_key=None` in the query string and the conditional `If-None-Match` header.

It reproduces exactly the surface ridewithgps.py touches:
  resp.info().getheader(name)   ridewithgps.py:99, 208
  resp.read()                   ridewithgps.py:100, 209
  urllib2.HTTPError with .code  ridewithgps.py:102-109
  socket.timeout                ridewithgps.py:110-112
"""
import socket
import urllib2


class StubResponse(object):
    def __init__(self, status, headers, body):
        self.status = status
        self._headers = headers or {}
        self._body = body if body is not None else ""

    def info(self):
        return self

    def getheader(self, name, default=None):
        # Real HTTP headers are case-insensitive and mimetools honors that.
        for k, v in self._headers.items():
            if k.lower() == name.lower():
                return v
        return default

    def read(self):
        body = self._body
        if isinstance(body, unicode):
            body = body.encode("utf-8")
        return body

    def close(self):
        pass


class ScriptedNet(object):
    """Installed over urllib2.urlopen for the duration of one fetch call."""

    def __init__(self, script):
        self.script = list(script or [])
        self.requests = []
        self._original = None

    # -- request recording ------------------------------------------------
    def _record(self, req, timeout):
        if isinstance(req, basestring):
            url, headers = req, {}
        else:
            url = req.get_full_url()
            # urllib2 title-cases header keys added via add_header().
            headers = dict(req.headers)
        self.requests.append({
            "url": url,
            "headers": headers,
            "timeout": timeout,
        })

    # -- the urlopen replacement ------------------------------------------
    def urlopen(self, req, timeout=None, **kwargs):
        self._record(req, timeout)
        n = len(self.requests) - 1
        if n >= len(self.script):
            raise AssertionError(
                "the code made %d requests but the script only defines %d; "
                "either the retry count changed or the script is short"
                % (n + 1, len(self.script)))
        step = self.script[n]

        kind = step.get("raise")
        if kind == "timeout":
            raise socket.timeout("timed out")
        if kind == "http":
            code = step.get("status", 404)
            raise urllib2.HTTPError(
                self.requests[-1]["url"], code, step.get("reason", "Error"),
                {}, None)
        if kind == "urlerror":
            raise urllib2.URLError(step.get("reason", "unreachable"))

        return StubResponse(step.get("status", 200),
                            step.get("headers"),
                            step.get("body"))

    # -- context management ------------------------------------------------
    def __enter__(self):
        self._original = urllib2.urlopen
        urllib2.urlopen = self.urlopen
        return self

    def __exit__(self, *exc):
        urllib2.urlopen = self._original
        return False
