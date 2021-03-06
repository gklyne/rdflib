
import os
import shutil
import tempfile
import warnings
from urlparse import urlparse
try:
    from io import BytesIO
    assert BytesIO
except:
    from StringIO import StringIO as BytesIO

from . import py3compat

__all__ = ['Processor', 'Result', 'ResultParser', 'ResultSerializer',
           'ResultException']


"""
Query plugin interface.

This module is useful for those wanting to write a query processor
that can plugin to rdf. If you are wanting to execute a query you
likely want to do so through the Graph class query method.

"""


class Processor(object):

    def __init__(self, graph):
        pass

    def query(self, strOrQuery, initBindings={}, initNs={}, DEBUG=False):
        pass


class ResultException(Exception):
    pass


class EncodeOnlyUnicode(object):
    """
    This is a crappy work-around for
    http://bugs.python.org/issue11649


    """

    def __init__(self, stream):
        self.__stream = stream

    def write(self, arg):
        if isinstance(arg, unicode):
            self.__stream.write(arg.encode("utf-8"))
        else:
            self.__stream.write(arg)

    def __getattr__(self, name):
        return getattr(self.__stream, name)


class ResultRow(tuple):
    """
    a single result row
    allows accessing bindings as attributes or with []

    >>> from rdflib import URIRef, Variable
    >>> rr=ResultRow({ Variable('a'): URIRef('urn:cake') }, [Variable('a')])

    >>> rr[0]
    rdflib.term.URIRef(%(u)s'urn:cake')
    >>> rr[1]
    Traceback (most recent call last):
        ...
    IndexError: tuple index out of range

    >>> rr.a
    rdflib.term.URIRef(%(u)s'urn:cake')
    >>> rr.b
    Traceback (most recent call last):
        ...
    AttributeError: b

    >>> rr['a']
    rdflib.term.URIRef(%(u)s'urn:cake')
    >>> rr['b']
    Traceback (most recent call last):
        ...
    KeyError: 'b'

    >>> rr[Variable('a')]
    rdflib.term.URIRef(%(u)s'urn:cake')


    """
    __doc__ = py3compat.format_doctest_out(__doc__)

    def __new__(cls, values, labels):

        instance = super(ResultRow, cls).__new__(
            cls, (values.get(v) for v in labels))
        instance.labels = dict((unicode(x[
                               1]), x[0]) for x in enumerate(labels))
        return instance

    def __getattr__(self, name):
        if name not in self.labels:
            raise AttributeError(name)
        return tuple.__getitem__(self, self.labels[name])

    def __getitem__(self, name):
        try:
            return tuple.__getitem__(self, name)
        except TypeError:
            if name in self.labels:
                return tuple.__getitem__(self, self.labels[name])
            if unicode(name) in self.labels:  # passing in variable object
                return tuple.__getitem__(self, self.labels[unicode(name)])
            raise KeyError(name)


class Result(object):
    """
    A common class for representing query result.
    This is backwards compatible with the old SPARQLResult objects
    Like before there is a bit of magic that makes this appear like Python
    objects, depending on the type of result.

    If the type is "SELECT", this is like a list of list of values
    If the type is "ASK" this is like a list of a single bool
    If the type is "CONSTRUCT" or "DESCRIBE" this is like a graph

    """
    def __init__(self, type_):

        if type_ not in ('CONSTRUCT', 'DESCRIBE', 'SELECT', 'ASK'):
            raise ResultException('Unknown Result type: %s' % type_)

        self.type = type_
        self.vars = None
        self.bindings = None
        self.askAnswer = None
        self.graph = None

    @staticmethod
    def parse(source, format='xml', **kwargs):
        from rdflib import plugin
        parser = plugin.get(format, ResultParser)()
        return parser.parse(source, **kwargs)

    def serialize(
            self, destination=None, encoding="utf-8", format='xml', **args):

        if self.type in ('CONSTRUCT', 'DESCRIBE'):
            return self.graph.serialize(
                destination, encoding=encoding, format=format, **args)

        """stolen wholesale from graph.serialize"""
        from rdflib import plugin
        serializer = plugin.get(format, ResultSerializer)(self)
        if destination is None:
            stream = BytesIO()
            stream2 = EncodeOnlyUnicode(stream)
            serializer.serialize(stream2, encoding=encoding, **args)
            return stream.getvalue()
        if hasattr(destination, "write"):
            stream = destination
            serializer.serialize(stream, encoding=encoding, **args)
        else:
            location = destination
            scheme, netloc, path, params, query, fragment = urlparse(location)
            if netloc != "":
                print("WARNING: not saving as location" +
                      "is not a local file reference")
                return
            fd, name = tempfile.mkstemp()
            stream = os.fdopen(fd, 'wb')
            serializer.serialize(stream, encoding=encoding, **args)
            stream.close()
            if hasattr(shutil, "move"):
                shutil.move(name, path)
            else:
                shutil.copy(name, path)
                os.remove(name)

    def __len__(self):
        if self.type == 'ASK':
            return 1
        elif self.type == 'SELECT':
            return len(self.bindings)
        else:
            return len(self.graph)

    def __iter__(self):
        if self.type in ("CONSTRUCT", "DESCRIBE"):
            for t in self.graph:
                yield t
        elif self.type == 'ASK':
            yield self.askAnswer
        elif self.type == 'SELECT':
            # To remain compatible with the old SPARQLResult behaviour
            # this iterates over lists of variable bindings
            for b in self.bindings:
                yield ResultRow(b, self.vars)

    def __getattr__(self, name):
        if self.type in ("CONSTRUCT", "DESCRIBE") and self.graph is not None:
            return self.graph.__getattr__(self, name)
        elif self.type == 'SELECT' and name == 'result':
            warnings.warn(
                "accessing the 'result' attribute is deprecated."
                " Iterate over the object instead.",
                DeprecationWarning, stacklevel=2)
            # copied from __iter__, above
            return [(tuple(b[v] for v in self.vars)) for b in self.bindings]
        else:
            raise AttributeError(
                "'%s' object has no attribute '%s'" % (self, name))

    def __eq__(self, other):
        try:
            if self.type != other.type:
                return False
            if self.type == 'ASK':
                return self.askAnswer == other.askAnswer
            elif self.type == 'SELECT':
                return self.vars == other.vars \
                    and self.bindings == other.bindings
            else:
                return self.graph == other.graph

        except:
            return False


class ResultParser(object):

    def __init__(self):
        pass

    def parse(self, source):
        """return a Result object"""
        pass  # abstract


class ResultSerializer(object):

    def __init__(self, result):
        self.result = result

    def serialize(self, stream, encoding="utf-8"):
        """return a string properly serialized"""
        pass  # abstract
