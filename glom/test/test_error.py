
import os
import re
import traceback

import pytest

from glom import glom, S, T, GlomError
from glom.core import format_oneline_trace, format_target_spec_trace, bbrepr

try:
    unicode
except NameError:
    unicode = str  # py3

# basic tests:

def test_good_error():
    target = {'data': [0, 1, 2]}

    with pytest.raises(GlomError):
        glom(target, ('data.3'))


def test_error():
    target = {'data': [0, 1, 2]}

    with pytest.raises(GlomError):
        glom(target, ('data', '3'))
    with pytest.raises(GlomError):
        glom(target, ('data', [(T.real, T.bit_length, T.image)]))


def test_unfinalized_glomerror_repr():
    assert 'GlomError()' in repr(GlomError())


# trace unit tests:

def test_line_trace():
    stacklifier = ([{'data': S}],)
    scope = glom([1], stacklifier)[0]['data']
    fmtd_stack = format_oneline_trace(scope)
    assert fmtd_stack == '/tuple!list/list<0>/dict!int/S'


def test_short_trace():
    stacklifier = ([{'data': S}],)
    scope = glom([1], stacklifier)[0]['data']
    fmtd_stack = format_target_spec_trace(scope)
    exp_lines = [
        " - Target: [1]",
        " - Spec: ([{'data': S}],)",
        " - Spec: [{'data': S}]",
        " - Target: 1",
        " - Spec: {'data': S}",
        " - Spec: S",
    ]
    assert fmtd_stack.splitlines() == exp_lines

# full traceback testing:

def _norm_stack(formatted_stack, exc):

    if not isinstance(formatted_stack, unicode):
        # lil hack for py2
        # note that we only support the one unicode character
        formatted_stack = formatted_stack.decode('utf8') .replace(r'\xc3\xa9', u'é')
        formatted_stack = re.sub(r'\bu"', '"', formatted_stack)
        formatted_stack = re.sub(r"\bu'", "'", formatted_stack)

    normalized = []
    for line in formatted_stack.splitlines():
        if line.strip().startswith(u'File'):
            file_name = line.split(u'"')[1]
            short_file_name = os.path.split(file_name.strip(u'"'))[1]
            line = line.replace(file_name, short_file_name)
            line = line.partition(u'line')[0] + u'line ___,' + line.partition(u'line')[2].partition(u',')[2]
        line = line.partition(u'0x')[0]  # scrub memory addresses

        line = line.rstrip()  # trailing whitespace shouldn't matter

        # qualify python2's unqualified error type names
        exc_type_name = exc.__class__.__name__
        if exc_type_name in line:
            mod_name = unicode(getattr(exc.__class__, '__module__', '') or '')
            exc_type_qual_name = exc_type_name
            if 'builtin' not in mod_name:
                exc_type_qual_name = mod_name + '.' + exc_type_name
            if exc_type_qual_name not in line:
                line = line.replace(exc_type_name, exc_type_qual_name)

        normalized.append(line)

    stack = u"\n".join(normalized) + u'\n'
    stack = stack.replace(u',)', u')')  # py37 likes to do Exception('msg',)
    return stack


def _make_stack(spec, **kwargs):
    target = kwargs.pop('target', [None])
    assert not kwargs
    try:
        glom(target, spec)
    except GlomError as e:
        stack = _norm_stack(traceback.format_exc(), e)
    return stack


# quick way to get a function in this file, which doesn't have a glom
# package file path prefix on it. this prevents the function getting
# removed in the stack flattening.
from boltons.funcutils import FunctionBuilder
fb = FunctionBuilder(name='_raise_exc',
                     body='raise Exception("unique message")',
                     args=['t'])
_raise_exc = fb.get_func()

# NB: if we keep this approach, eventually
# boltons.funcutils.FunctionBuilder will put lines into the linecache,
# and comparisons may break


def test_regular_error_stack():
    actual = _make_stack({'results': [{'value': _raise_exc}]})
    expected = """\
Traceback (most recent call last):
  File "test_error.py", line ___, in _make_stack
    glom(target, spec)
  File "core.py", line ___, in glom
    raise err
glom.core.GlomError.wrap(Exception): error raised while processing.
 Target-spec trace, with error detail (most recent last):
 - Target: [None]
 - Spec: {'results': [{'value': <function _raise_exc at
 - Spec: [{'value': <function _raise_exc at
 - Target: None
 - Spec: {'value': <function _raise_exc at
 - Spec: <function _raise_exc at
  File "<boltons.funcutils.FunctionBuilder-0>", line ___, in _raise_exc
Exception: unique message
"""
    # _raise_exc being present in the second-to-last line above tests
    # that errors in user-defined functions result in frames being
    # visible
    assert expected == actual


def test_glom_error_stack():
    # NoneType has not attribute value
    expected = u"""\
Traceback (most recent call last):
  File "test_error.py", line ___, in _make_stack
    glom(target, spec)
  File "core.py", line ___, in glom
    raise err
glom.core.PathAccessError: error raised while processing.
 Target-spec trace, with error detail (most recent last):
 - Target: [None]
 - Spec: {'results': [{'valué': 'value'}]}
 - Spec: [{'valué': 'value'}]
 - Target: None
 - Spec: {'valué': 'value'}
 - Spec: 'value'
glom.core.PathAccessError: could not access 'value', part 0 of Path('value'), got error: AttributeError("'NoneType' object has no attribute 'value'")
"""
    #import glom.core
    #glom.core.GLOM_DEBUG = True
    actual = _make_stack({'results': [{u'valué': u'value'}]})
    print(actual)
    assert expected == actual


# used by the test below, but at the module level to make stack traces
# more uniform between py2 and py3 (py3 tries to qualify lambdas and
# other functions inside of local scopes.)

def _uses_another_glom():
    try:
        ret = glom(['Nested'], {'internal': ['val']})
    except Exception as exc:
        raise


def _subglom_wrap(t):
    return _uses_another_glom()


def test_glom_error_double_stack():
    actual = _make_stack({'results': [{'value': _subglom_wrap}]})
    expected = """\
Traceback (most recent call last):
  File "test_error.py", line ___, in _make_stack
    glom(target, spec)
  File "core.py", line ___, in glom
    raise err
glom.core.PathAccessError: error raised while processing.
 Target-spec trace, with error detail (most recent last):
 - Target: [None]
 - Spec: {'results': [{'value': <function _subglom_wrap at
 - Spec: [{'value': <function _subglom_wrap at
 - Target: None
 - Spec: {'value': <function _subglom_wrap at
 - Spec: <function _subglom_wrap at
glom.core.PathAccessError: error raised while processing.
 Target-spec trace, with error detail (most recent last):
 - Target: ['Nested']
 - Spec: {'internal': ['val']}
 - Spec: ['val']
 - Target: 'Nested'
 - Spec: 'val'
glom.core.PathAccessError: could not access 'val', part 0 of Path('val'), got error: AttributeError("'str' object has no attribute 'val'")
"""
    assert expected == actual


def test_long_target_repr():
    import glom as glom_mod
    assert not glom_mod.core.GLOM_DEBUG
    actual = _make_stack(target=[None] * 1000, spec='1001')
    assert '(len=1000)' in actual

    class ObjectWithLongRepr(object):
        def __repr__(self):
            return '<%s %s>' % (self.__class__.__name__, 'w' + ('ooooo' * 250))

    actual = _make_stack(target=ObjectWithLongRepr(), spec='badattr')
    assert '...' in actual
    assert '(len=' not in actual  # no length on a single object



ERROR_CLASSES = (
    ValueError, NameError, AttributeError, ZeroDivisionError, SyntaxError, ImportError)

def test_error_types():
    """test that try / except work normally through glom"""
    for err_class in ERROR_CLASSES:
        def err_raise(t):
            raise err_class()
        with pytest.raises(err_class):
            glom(None, err_raise)


def test_fallback():
    """
    test that in cases of weird badly behaved exception types,
    the handler falls back from wrapping to just letting the exception
    through
    """
    class BadExc(Exception):
        def __init__(self, first):
            if not first:
                1/0
            self.first = False
            super(BadExc, self).__init__(self.first)

    bad_exc = BadExc(True)

    def raise_bad(t):
        raise bad_exc

    try:
        glom(None, raise_bad)
    except Exception as e:
        assert e is bad_exc


def test_all_public_errors():
    """test that all errors importable from the top-level glom module
    pass a basic set of standards.

    When adding a new public error type, this test will be fail unless
    that type is also tested below.
    """
    import glom
    import copy

    err_types = [t for t in
                 [getattr(glom, name) for name in dir(glom)]
                 if isinstance(t, type) and issubclass(t, Exception)]
    non_glomerrors = [t for t in err_types if not issubclass(t, glom.GlomError)]
    assert not non_glomerrors, "expected all public exception types to subclass GlomError"

    err_types = sorted([t for t in err_types if not t is glom.GlomError],
                       key=lambda t: t.__name__)

    results = []

    def _test_exc(exc_type, target, spec):
        with pytest.raises(exc_type) as exc_info:
            glom.glom(target, spec)
        results.append((target, spec, exc_info.value))
        return exc_info.value

    _test_exc(glom.CheckError, {}, glom.Check(equal_to=[]))

    _test_exc(glom.FoldError, 2, glom.Flatten())

    _test_exc(glom.BadSpec, range(5), glom.grouping.Group([{T: T}]))

    _test_exc(glom.PathAccessError, {}, 'a.b.c')

    _test_exc(glom.UnregisteredTarget, 'kurt', [glom.T])

    _test_exc(glom.CoalesceError, {}, glom.Coalesce('a', 'b'))

    _test_exc(glom.PathAssignError, object(), glom.Assign('a', 'b'))

    _test_exc(glom.PathDeleteError, object(), glom.Delete('a'))

    for (target, spec, exc) in results:
        assert copy.copy(exc) is not exc
        exc_str = str(exc)
        exc_type_name = exc.__class__.__name__
        assert exc_type_name in exc_str
        assert bbrepr(exc).startswith(exc_type_name)

        assert bbrepr(target)[:80] in exc_str
        assert bbrepr(spec)[:80] in exc_str

    tested_types = [type(exc) for _, _, exc in results]
    untested_types = set(err_types) - set(tested_types)

    assert not untested_types, "did not test all public exception types"


def test_glom_dev_debug():
    with pytest.raises(GlomError) as exc_info:
        glom({'a': 'yesandno'}, 'a.b.c')

    assert ' - Target:' in str(exc_info.value)
    assert 'yesandno' in str(exc_info.value)
    assert len(exc_info.traceback) == 2

    with pytest.raises(GlomError) as exc_info:
        glom({'a': 'yesandno'}, 'a.b.c', glom_debug=True)

    assert ' - Target:' not in str(exc_info.value)
    assert len(exc_info.traceback) > 2


def test_unicode_stack():
    val = {u'resumé': u'beyoncé'}
    stack = _make_stack(target=val, spec=u'a.é.i.o')
    assert 'beyonc' in stack
    assert u'é' in stack
