from typing import List, Tuple
from construct.core import Construct
import pytest
from construct import Byte, Struct
from constructutils import InlineError, InliningStruct, InlineStruct


data: List[Tuple[Construct, dict, bytes]] = [
    (
        InliningStruct(
            'a' / Byte
        ),
        {'a': 1},
        b'\x01'
    ),
    (
        InliningStruct(
            InlineStruct('a' / Byte)
        ),
        {'a': 1},
        b'\x01'
    ),
    (
        InliningStruct(
            'a' / Byte,
            'struct' / Struct('a' / Byte),
            InlineStruct('b' / Byte, 'c' / Byte),
            'd' / Byte
        ),
        {'a': 1, 'struct': {'a': 2}, 'b': 3, 'c': 4, 'd': 5},
        b'\x01\x02\x03\x04\x05'
    )
]


@pytest.mark.parametrize('struct, expected, data', data)
def test_parse(data, struct, expected):
    assert struct.parse(data) == expected


@pytest.mark.parametrize('struct, value, expected', data)
def test_build(value, struct, expected):
    assert struct.build(value) == expected


def test_duplicate():
    s = InliningStruct(
        'a' / Byte,
        InlineStruct(
            'a' / Byte
        )
    )
    assert s.parse(b'\x01\x02') == {'a': 2}
    assert s.build({'a': 1}) == b'\x01\x01'


def test_noinlining():
    s = Struct(
        InlineStruct('a' / Byte)
    )
    with pytest.raises(InlineError):
        s.parse(b'x')
    with pytest.raises(KeyError):
        s.build({'a': b'x'})
