import io
import pytest
import functools
import collections
from construct import Array, Byte, Container

from constructutils import AttributeRawCopy
from constructutils.misc import \
    DictZipAdapter, \
    SwitchKeyError, SwitchNoDefault, \
    seek_temporary, \
    iter_context_tree, get_root_context, get_root_stream


def test_dictzipadapter():
    s = DictZipAdapter(['a', 'b'], Array(2, Byte))
    data = b'\x01\x02'
    value = collections.OrderedDict({'a': 1, 'b': 2})

    assert s.parse(data) == value
    assert s.build(value) == data


def test_dictzipadapter_rawcopy():
    s = DictZipAdapter(
        ['a', 'b'],
        AttributeRawCopy(Array(2, Byte))
    )
    value = s.parse(b'\x01\x02')

    assert value == {'a': 1, 'b': 2}
    assert value.__raw__ == b'\x01\x02'


def test_switchnodefault():
    get_s = functools.partial(SwitchNoDefault, cases={0: Byte})

    s_valid = get_s(0)
    assert s_valid.parse(b'\x01') == 0x01
    assert s_valid.build(0x01) == b'\x01'

    s_invalid = get_s(1)
    with pytest.raises(SwitchKeyError):
        s_invalid.parse(b'\x01')
    with pytest.raises(SwitchKeyError):
        s_invalid.build(0x01)


def test_seek_temporary():
    stream = io.BytesIO()
    stream.write(b'000')
    with seek_temporary(stream, '', 1):
        assert stream.tell() == 1
    assert stream.tell() == 3


def __get_test_tree():
    c4 = Container()
    c3 = Container(_=c4, _io=object())
    c2 = Container(_=c3)
    c1 = Container(_=c2, _io=object(), _root=c4)
    return c1


def test_iter_context_tree():
    t = __get_test_tree()
    assert list(iter_context_tree(t)) == [t, t._, t._._, t._._._]


def test_get_root_context():
    t = __get_test_tree()
    assert get_root_context(t) == t._._._


def test_get_root_stream():
    t = __get_test_tree()
    assert get_root_stream(t) == t._._._io
