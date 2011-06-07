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
    yield """<!--
browsers won't actually display data as it comes in until there is a certain
minimal amount already received, so this prefix is just to send something to
push the browser over that limit so that the stuff we care about will be
rendered immediately.

nope, the previous paragraph wasn't enough (for chrome at least). so, what's
new with you? *sigh*, this forced conversation just feels so awkward.

it's ok, we ALREADY have around 40% of the padding we need! I think I'll take
the rest of our time together to berate browsers for this behavior.

"Transfer-Encoding: chunked" has obvious intention, and paricularly obvious
implications for pieces that are going to be displayed on the screen. It's a
clear statement that things might take a while so why don't you just go ahead
and display what you receive as you receive it. It's a perfectly reasonable
means of getting HTTP server-push that is hampered by this browser behavior,
and for the life of me I can't figure out why it would be a good idea.

glad I got that off my chest.
-->
<!DOCTYPE html>
<html>
\t<body>
"""
    for i in xrange(10):
        greenhouse.pause_for(1)
        yield "\t\t<p>%d</p>\n" % i
    yield "\t</body>\n</html>"


if __name__ == '__main__':
    serve(("localhost", 9090), app, worker_count=1, traceback_body=True)
