import os
import pytest
from construct import \
    Struct, Tell, GreedyBytes, Byte, Array, Computed, Prefixed, \
    SizeofError, this
from constructutils import DeferredError, DeferredValue, WriteDeferredValue, CheckDeferredValues


def test_placeholder():
    assert DeferredValue(Byte, 0xff).build(None) == b'\xff'


def test_single():
    s = Struct(
        'a' / Byte,
        'b' / DeferredValue(Byte, 0xff),
        'c' / Byte,
        'new_value' / Tell,
        WriteDeferredValue(this.new_value, this.b)
    )

    # parsing
    assert s.parse(b'\x01\x02\x03') == {'a': 1, 'b': 2, 'c': 3, 'new_value': 3}

    # building
    assert s.build({'a': 0xff, 'c': 0xfe}) == b'\xff\x03\xfe'


def test_nested():
    s = Struct(
        'a' / Byte,
        'b' / DeferredValue(Byte, 0xff),
        'c' / Byte,
        'struct' / Struct(
            'new_value' / Tell,
            WriteDeferredValue(this.new_value + 7, this._.b),
            'x' / Byte
        )
    )

    # parsing
    assert s.parse(b'\x01\x02\x03\x04') == {'a': 1, 'b': 2, 'c': 3, 'struct': {'new_value': 3, 'x': 4}}

    # building
    assert s.build({'a': 0xff, 'c': 0xfe, 'struct': {'x': 0x42}}) == b'\xff\x0a\xfe\x42'


def test_complex_prefixed():
    s = Struct(
        'v' / Byte,
        'a1' / Prefixed(Byte, Array(2, Struct(
            'value' / DeferredValue(Byte, 0x00)
        ))),
        'a2' / Array(2, Struct(
            '@offset' / Tell,
            WriteDeferredValue(this['@offset'], lambda this: this._.a1[this._index].value),
            'value' / Byte
        ))
    )

    # parsing
    assert s.parse(b'\xff\x02\x41\x42\xe0\xe1') == {
        'v': 0xff,
        'a1': [
            {'value': 0x41},
            {'value': 0x42}
        ],
        'a2': [
            {'@offset': 4, 'value': 0xe0},
            {'@offset': 5, 'value': 0xe1}
        ]
    }

    # building
    assert s.build({
        'v': 0xff,
        'a1': [
            {},
            {}
        ],
        'a2': [
            {'value': 0xe0},
            {'value': 0xe1}
        ]
    }) == b'\xff\x02\x04\x05\xe0\xe1'


def test_constant_size():
    with pytest.raises(DeferredError) as e:
        DeferredValue(GreedyBytes, b'')
    assert isinstance(e.value.__context__, SizeofError)


def test_unexpected_placeholder():
    def _change_placeholder(context):
        stream = context._io
        stream.seek(-1, os.SEEK_CUR)
        stream.write(b'\xff')

    s = Struct(
        'a' / DeferredValue(Byte, 0x00),
        Computed(_change_placeholder),  # overwrites 0x00 with 0xff, should fail sanity check later
        WriteDeferredValue(0x42, this.a)
    )

    with pytest.raises(DeferredError):
        s.build({})


def test_build_no_value():
    s = Struct(
        'a' / DeferredValue(Byte, 0x00),
        WriteDeferredValue(0x42, this.a)
    )

    with pytest.raises(DeferredError):
        s.build({'a': 0xab})


def test_build_invalid_target():
    s = Struct(
        'a' / Byte,
        WriteDeferredValue(0x42, this.a)
    )

    with pytest.raises(DeferredError):
        s.build({'a': 0xff})


def test_check_deferred():
    s = Struct(
        'a' / DeferredValue(Byte, 0x00),
        CheckDeferredValues
    )

    with pytest.raises(DeferredError):
        s.build({})
