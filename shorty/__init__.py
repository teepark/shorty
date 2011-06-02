from __future__ import absolute_import

import BaseHTTPServer
import cgi
import collections
import Cookie
import email.feedparser
import functools
import itertools
import re
import urlparse
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
        self.COOKIES = Cookie.SimpleCookie(environ.get('HTTP_COOKIE', ''))
        self.PATH = environ['PATH_INFO']

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

        if environ.get('REQUEST_METHOD', '').upper() not in ('POST', 'PUT'):
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
            bound = options.get('boundary', '')
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
            while chunk:
                data.write(chunk)
                chunk = environ['wsgi.input'].read(8192)
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

    def redirect(self, location, code=301):
        self.add_header("Location", location)
        raise Error(code, '')


class _MethodDescriptor(object):
    def __init__(self, method):
        self.method = method

    def __get__(self, instance, owner):
        if instance is None:
            return self

        return functools.partial(self.HandlerWrapper, self.method, instance)

    class HandlerWrapper(object):
        def __init__(self, method, app, urlpath):
            self.method = method
            self.app = app
            self.urlpath = urlpath

        def __call__(self, handler):
            self.app.handlers[self.method.upper()].append(
                    (re.compile(self.urlpath), handler))
            return handler


class App(object):

    get = _MethodDescriptor("GET")
    post = _MethodDescriptor("POST")
    head = _MethodDescriptor("HEAD")
    put = _MethodDescriptor("PUT")
    delete = _MethodDescriptor("DELETE")

    def __init__(self):
        self.handlers = collections.defaultdict(list)

    def __call__(self, environ, start_response):
        handler, args, kwargs = self._resolve(environ)
        http = HTTP(environ)
        if handler:
            try:
                message = handler(http, *args, **kwargs)
                status = http._out_code
            except Error, err:
                status = err.status
                message = err.message
                if message is None:
                    message = RESPONSES[status][1]
        else:
            status = 404
            message = RESPONSES[status][1]

        # pull the first chunk so that a generator at least gets entered
        if hasattr(message, "__iter__"):
            for first_chunk in message:
                break
            message = itertools.chain([first_chunk], message)

        # is this really a good place for setting the Set-Cookie header?
        if http.COOKIES:
            http.add_header(*(http.COOKIES.output().split(": ", 1)))

        if (isinstance(message, str)
                and not any(1 for x in http._out_headers
                        if x[0].lower() == 'content-length')):
            http.add_header('Content-Length', str(len(message)))

        start_response(
                "%d %s" % (status, RESPONSES[status][0]), http._out_headers)

        if not hasattr(message, "__iter__"):
            message = [message]
        return message

    def _resolve(self, environ):
        for regex, handler in self.handlers[environ['REQUEST_METHOD'].upper()]:
            match = regex.match(environ['PATH_INFO'])
            if match:
                kwargs = match.groupdict()
                args = not kwargs and match.groups() or ()
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
