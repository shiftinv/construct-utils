import pytest
from construct import Struct, Array, Byte
from constructutils import RawCopyError, AttributeRawCopy


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


def test_build():
    # should pass data to subcon
    s = AttributeRawCopy(Array(3, Byte))
    assert s.build([1, 2, 3]) == b'\x01\x02\x03'


def test_unsupported_subcon():
    with pytest.raises(RawCopyError):
        AttributeRawCopy(Byte)


def test_duplicate():
    s = Struct(
        'value' @ AttributeRawCopy(Struct(
            'value' / Byte
        ))
    )
    with pytest.raises(RawCopyError):
        s.parse(b'0')
