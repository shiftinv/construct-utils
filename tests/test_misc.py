import io
import pytest
import functools
import collections
from enum import Enum
from construct import Struct, Array, Byte, Container, Computed, MappingError

from constructutils import AttributeRawCopy
from constructutils.misc import \
    DictZipAdapter, \
    EnumConvert, \
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


def test_enumconvert():
    class TestEnum(Enum):
        A = 0x42

        @property
        def prop(self):
            return 1337

    s = Struct(
        'e' / EnumConvert(Byte, TestEnum),
        'v' / Computed(lambda this: this.e.prop)
    )

    # valid
    assert s.parse(b'\x42') == {'e': TestEnum.A, 'v': 1337}
    assert s.build({'e': TestEnum.A}) == b'\x42'

    # invalid
    with pytest.raises(MappingError):
        s.parse(b'\x00')
    with pytest.raises(MappingError):
        s.build({'e': 0})


def test_enumconvert_type():
    with pytest.raises(MappingError):
        EnumConvert(Byte, dict)  # type: ignore


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
