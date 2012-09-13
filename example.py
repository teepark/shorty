#!/usr/bin/env python
# vim: fileencoding=utf8:et:sta:ai:sw=4:ts=4:sts=4

import pprint
import traceback

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
    # potential XSS hole (though the regex should be strict enough)
    return "<h1>Hello, %s</h1>" % name

@app.get("^/headers/$")
def headers(http):
    http.add_header("content-type", "text/plain")
    return pprint.pformat(http.headers.items())

@app.get("^/cookies/$")
def cookies(http):
    http.add_header("content-type", "text/plain")
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
    http.COOKIES[http.POST['name']]['path'] = '/'
    http.redirect("/cookies/")

@app.get("^/del_cookies/$")
def del_cookies(http):
    for key in http.COOKIES:
        http.COOKIES[key] = ""
        morsel = http.COOKIES[key]
        morsel['max-age'] = morsel['expires'] = 0
        morsel['path'] = '/'
    http.redirect("/cookies/")

@app.get("^/chunked/$")
@app.chunked
def chunked_response(http):
    http.add_header('content-type', 'text/html')
    yield """<!DOCTYPE html>
<html>
\t<body>
<!--%s--!>
""" % (' ' * (1024 - 40))
    for i in xrange(10):
        greenhouse.pause_for(1)
        yield "\t\t<p>%d</p>\n" % i
    yield "\t</body>\n</html>"

@app.get("^/fail/$")
def fail(http):
    raise Exception("omg I broke")

@app.handle_500
def on_failure(http, triple):
    http.add_header('content-type', 'text/plain')
    return ("An Error Occurred:\n\n"
            + ''.join(traceback.format_exception(*triple)))

subapp = App()

@app.get("^/subapp")
def delegate_to_subapp(http):
    return subapp

@subapp.get("/$")
def subapp_index(http):
    return "index of the sub-app"

@subapp.get("/hello/world/$")
def subapp_helloworld(http):
    return "<p>subapp says:</p><h2>Hello, World!</h2>"


if __name__ == '__main__':
    serve(("localhost", 9090), app, worker_count=1, traceback_body=True)
