from construct import Struct, Byte

from constructutils import _global_struct_io_patch


def test_main():
    s = Struct('a' / Byte)

    # original behavior
    _global_struct_io_patch.unpatch()
    try:
        value = s.parse(b'\x01')
        assert '_io' in value
    finally:
        _global_struct_io_patch.patch()

    # patched
    value = s.parse(b'\x01')
    assert '_io' not in value


def test_duplicate():
    f = Struct._parse
    _global_struct_io_patch.patch()
    # make sure function isn't patched twice
    assert f == Struct._parse
