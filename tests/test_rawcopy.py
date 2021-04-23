import pytest
from construct import Struct, Array, Byte, Computed, this

from constructutils import \
    RawCopyError, AttributeRawCopy, \
    InliningStruct, InlineStruct


def test_parse():
    rawcopy = AttributeRawCopy(Array(3, Byte))

    # test default and custom name
    for name in [None, 'newname']:
        subcon = (name @ rawcopy) if name is not None else rawcopy
        s = Struct(
            'num' / Byte,
            'array' / subcon
        )

        value = s.parse(b'\xff\x01\x02\x03')
        assert value.num == 0xff
        assert value.array == [1, 2, 3]
        assert getattr(value.array, '__raw__' if name is None else name) == b'\x01\x02\x03'


def test_parse_construct():
    s = '__raw__' @ AttributeRawCopy(Struct('a' / Byte))

    value = s.parse(b'\xff')
    assert value == {'a': 0xff}
    assert value.__raw__ == b'\xff'

    # make sure that raw data would not be returned when iterating over dict/container
    assert '__raw__' not in value


def test_build():
    # should pass data to subcon
    s = AttributeRawCopy(Array(3, Byte))
    assert s.build([1, 2, 3]) == b'\x01\x02\x03'


def test_duplicate():
    s = Struct(
        'value' @ AttributeRawCopy(Struct(
            'value' / Byte
        ))
    )
    with pytest.raises(RawCopyError):
        s.parse(b'0')


def test_inline():
    s = InliningStruct(
        'raw' @ AttributeRawCopy(InlineStruct(
            'a' / Byte
        )),
        # make sure `this.raw` is accessible from inside the `InliningStruct` while it's still parsing/building
        'b' / Computed(this.raw)
    )

    value = s.parse(b'\x01')
    assert value == {'a': 1, 'b': b'\x01'}
    assert value.raw == b'\x01'

    assert s.build({'a': 1}) == b'\x01'
