from __future__ import absolute_import

import BaseHTTPServer
import cgi
import collections
import Cookie
import itertools
import re
import sys
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from . import multipart


__all__ = ["App", "Error"]

RESPONSES = BaseHTTPServer.BaseHTTPRequestHandler.responses
NOT_SUPPLIED = object()


class HTTP(object):
    def __init__(self, environ):
        self.environ = environ
        self.COOKIES = ChangeDetectingCookie(environ.get('HTTP_COOKIE', ''))
        self.PATH = environ['PATH_INFO']
        self.METHOD = environ['REQUEST_METHOD'].upper()

        self._out_headers = []
        self._out_code = 200

        headerlist = [
                (k[5:].replace('_', '-'), v.lstrip(' '))
                for k, v in environ.iteritems()
                if k.startswith("HTTP_")]
        self.headers = multipart.MultiDict(headerlist)

        get_params = cgi.parse_qsl(
                environ.get('QUERY_STRING', ''), keep_blank_values=True)

        self.GET = multipart.MultiDict(get_params)
        self.POST = multipart.MultiDict()
        self.FILES = multipart.MultiDict()
        self.BODY = environ['wsgi.input']

        if environ['REQUEST_METHOD'].upper() not in ('POST', 'PUT'):
            return

        content_length = environ.get('CONTENT_LENGTH', '')
        if not (isinstance(content_length, (int, long)) \
                or content_length.isdigit()):
            return

        content_length = int(content_length)
        content_type, ctype_options = multipart.parse_options_header(
                environ.get('CONTENT_TYPE', ''))
        charset = ctype_options.get('charset', 'utf8')

        if content_type == 'multipart/form-data':
            bound = ctype_options.get('boundary', '')
            if not bound:
                return
            parser = multipart.MultipartParser(environ['wsgi.input'], bound,
                    content_length, charset=charset)
            for part in parser:
                if part.filename or not part.is_buffered():
                    self.FILES[part.name] = part
                else:
                    self.POST[part.name] = part.value
        elif content_type in ('application/x-www-form-urlencoded',
                'application/x-url-encoded'):
            data = StringIO()
            chunk = environ['wsgi.input'].read(8192)
            total = len(chunk)
            while chunk:
                data.write(chunk)
                chunk = environ['wsgi.input'].read(8192)
                total += len(chunk)
            if total < content_length:
                # if we got an incomplete body, don't provide *any* body
                return
            self.POST = multipart.MultiDict(
                    cgi.parse_qsl(data.getvalue(), keep_blank_values=True))

    @property
    def url(self):
        path = urllib.quote(self.environ['SCRIPT_NAME'] +
                self.environ['PATH_INFO'])

        query = ""
        if self.environ.get('QUERY_STRING'):
            query = "?" + self.environ['QUERY_STRING']

        return path + query

    @property
    def absolute_url(self):
        scheme = self.environ['wsgi.url_scheme']

        if 'HOST' in self.headers:
            host = self.headers['HOST'][0]
        else:
            host = self.environ['SERVER_NAME']
            port = self.environ['SERVER_PORT']
            if (host, port) not in [('http', '80'), ('https', '443')]:
                host = '%s:%s' % (host, port)

        return "%s://%s%s" % (scheme, host, self.url)

    def add_header(self, key, value):
        self._out_headers.append((key, value))

    def set_code(self, code):
        self._out_code = code

    def redirect(self, location, code=302):
        self.add_header("Location", location)
        raise Error(code, '')


class App(object):
    def __init__(self):
        self.handlers = collections.defaultdict(list)
        self.handler_404 = None
        self.handler_500 = None

    def add_handler(self, method, pattern):
        def addme(func):
            self.handlers[method].append((re.compile(pattern), func))
            return func
        return addme

    def get(self, pattern): return self.add_handler("GET", pattern)
    def post(self, pattern): return self.add_handler("POST", pattern)
    def head(self, pattern): return self.add_handler("HEAD", pattern)
    def put(self, pattern): return self.add_handler("PUT", pattern)
    def delete(self, pattern): return self.add_handler("DELETE", pattern)

    def handle_500(self, func):
        self.handler_500 = func
        return func

    def handle_404(self, func):
        self.handler_404 = func
        return func

    def __call__(self, environ, start_response):
        handler, args, kwargs = self._resolve(environ)

        if 'routing.http' in environ:
            http = environ['routing.http']
        else:
            http = HTTP(environ)
            environ['routing.http'] = http
        if handler:
            try:
                message = handler(http, *args, **kwargs)
                status = http._out_code
            except Error, err:
                status = err.status
                message = err.message
                if message is None:
                    message = RESPONSES[status][1]
            except Exception:
                if self.handler_500 is None:
                    raise
                http.set_code(500)
                message = self.handler_500(http, sys.exc_info())
                status = http._out_code
        else:
            status = 404
            message = RESPONSES[status][1]
            if self.handler_404 is not None:
                message = self.handler_404(http)

        if isinstance(message, App):
            environ['routing.http'] = http
            return message(environ, start_response)

        # pull the first chunk so that a generator at least gets entered
        if hasattr(message, "__iter__"):
            iterator = iter(message)
            try:
                prefix = [iterator.next()]
            except StopIteration:
                prefix = []
            message = itertools.chain(prefix, iterator)

        for value in http.COOKIES.updated():
            http.add_header('Set-Cookie', str(value.output(header='')))

        if (isinstance(message, str)
                and not any(k.lower() == 'content-length'
                    for k, v in http._out_headers)):
            http.add_header('Content-Length', str(len(message)))

        start_response(
                "%d %s" % (status, RESPONSES[status][0]), http._out_headers)

        # never send a body on HEAD requests.
        # do it this late so that the Content-Length header
        # still reflects what the length *would have* been
        if http.METHOD == 'HEAD':
            message = ''

        if not hasattr(message, "__iter__"):
            message = [message]

        return message

    def _resolve(self, environ):
        path = environ.get('routing.remaining_path', environ['PATH_INFO'])
        for regex, handler in self.handlers[environ['REQUEST_METHOD'].upper()]:
            match = regex.match(path)
            if match:
                environ['routing.remaining_path'] = \
                        path[:match.start()] + path[match.end():]
                kwargs = match.groupdict()
                args = () if kwargs else match.groups()
                return handler, args, kwargs
        return None, (), {}

    def _gen_chunked(self, gen):
        for chunk in gen:
            # skip empty chunks
            if not chunk:
                continue
            yield '%x\r\n%s\r\n' % (len(chunk), chunk)
        yield '0\r\n\r\n'

    def chunked(self, func):
        def inner(http, *args, **kwargs):
            gen = func(http, *args, **kwargs)
            if not hasattr(gen, '__iter__'):
                return gen

            http.add_header('Transfer-Encoding', 'chunked')
            return self._gen_chunked(gen)

        return inner

class Error(Exception):
    def __init__(self, status, message=None):
        super(Error, self).__init__(status, message)
        self.status = status
        self.message = message


def _hash_morsel(morsel):
    return hash((morsel.coded_value,) + tuple(sorted(dict(morsel).items())))

class ChangeDetectingCookie(Cookie.SimpleCookie):
    def __init__(self, *args, **kwargs):
        super(ChangeDetectingCookie, self).__init__(*args, **kwargs)
        self._stamps = dict((k, _hash_morsel(m)) for k, m in self.items())

    def updated(self, deleted=True):
        # yield all the morsels added or updated
        for key, morsel in self.iteritems():
            if _hash_morsel(morsel) != self._stamps.get(key):
                yield morsel

        if deleted:
            # yield timed-out morsels for all those deleted
            for key, stamp in self._stamps.iteritems():
                if key not in self:
                    morsel = Cookie.Morsel()
                    morsel.set(key, "", "")
                    morsel['expires'] = morsel['max-age'] = 0
                    yield morsel
