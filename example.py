#!/usr/bin/env python
# vim: fileencoding=utf8:et:sta:ai:sw=4:ts=4:sts=4

import pprint

from feather.wsgi import serve
import greenhouse

from shorty import App


app = App()

@app.get("^(.*[^/])$")
def append_slash(http, path):
    http.redirect(path + "/")

@app.get("^/hello/world/$")
def hello(http):
    return "<p>Hello, World!</p>"

@app.get(r"^/hello/(\w+)/$")
def hello_anyone(http, name):
    # potential XSS hole
    return "<h1>Hello, %s</h1>" % name

@app.get("^/headers/$")
def headers(http):
    http.add_header("content-type", "text/plain")
    return pprint.pformat(http.headers.items())

@app.get("^/cookies/$")
def cookies(http):
    http.add_header("content-type", "text/plain")
    print http.headers.keys()
    return "\n".join(
            "%s: %s" % (k, v.value) for k, v in http.COOKIES.items())

@app.get("^/write_cookie/$")
def write_cookie(http):
    http.add_header('content-type', 'text/html')
    return '''<form method="POST" action="/write_cookie/">
    <input type="text" name="name"/><br>
    <input type="text" name="value"/>
    <input type="submit"/>
</form>'''

@app.post("^/write_cookie/$")
def write_cookie_post(http):
    http.COOKIES[http.POST['name']] = http.POST['value']
    http.redirect("/cookies/", 302)

@app.get("^/chunked/$")
@app.chunked
def chunked_response(http):
    http.add_header('content-type', 'text/html')
    # browsers won't display data as it comes in until there is a certain
    # minimal amount, so we prefix a bunch of junk to trigger that state early
    yield (" " * 1000) + "\n<!doctype html>\n<html>\n\t<body>\n"
    for i in xrange(10):
        greenhouse.pause_for(1)
        yield "\t\t<p>%d</p>\n" % i
    yield "\t</body>\n</html>"


if __name__ == '__main__':
    serve(("localhost", 9090), app, worker_count=1, traceback_body=True)
