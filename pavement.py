from paver.easy import *
from paver.path import path
from paver.setuputils import setup


VERSION = (0, 1, 0, "")

setup(
    name="routing",
    description="",
    packages=["routing"],
    version=".".join(filter(None, map(str, VERSION))),
    author="Travis Parker",
    author_email="travis.parker@gmail.com",
    url="http://github.com/teepark/shorty",
    license="BSD",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Natural Language :: English",
        "Programming Language :: Python",
    ],
)

MANIFEST = (
    "setup.py",
    "paver-minilib.zip",
)

@task
def manifest():
    path('MANIFEST.in').write_lines('include %s' % x for x in MANIFEST)

@task
@needs('generate_setup', 'minilib', 'manifest', 'setuptools.command.sdist')
def sdist():
    pass

@task
def clean():
    for p in map(path, (
        'routing.egg-info', 'dist', 'build', 'MANIFEST.in', 'docs/build')):
        if p.exists():
            if p.isdir():
                p.rmtree()
            else:
                p.remove()
    for p in path(__file__).abspath().parent.walkfiles():
        if p.endswith(".pyc") or p.endswith(".pyo"):
            p.remove()

@task
def docs():
    sh("find docs -name *.rst | xargs touch")
    sh("cd docs; make html")

@task
def test():
    sh("nosetests --processes=8")
