import pytest
import hashlib
from construct import Struct, Bytes, this

from constructutils import \
    ChecksumCalcError, ChecksumVerifyError, \
    ChecksumValue, ChecksumSourceData, VerifyOrWriteChecksums


test_struct = Struct(
    'hash' / ChecksumValue(hashlib.sha1, this.data),
    'data' / ChecksumSourceData(Struct(
        'x' / Bytes(4)
    )),
    VerifyOrWriteChecksums
)
test_data = hashlib.sha1(b'test').digest() + b'test'


def test_parse_valid():
    assert test_struct.parse(test_data) == {
        'hash': test_data[:-4],
        'data': {'x': b'test'}
    }


def test_parse_invalid():
    mod_data = bytearray(test_data)
    mod_data[0] = (mod_data[0] + 1) & 0xff

    with pytest.raises(ChecksumVerifyError) as e:
        test_struct.parse(mod_data)
    assert e.value.expected == mod_data[:-4]
    assert e.value.actual == test_data[:-4]


def test_build():
    assert test_struct.build({'data': {'x': b'test'}}) == test_data


def test_no_sourcedata():
    s = Struct(
        'hash' / ChecksumValue(hashlib.sha1, this.data),
        'data' / Struct(
            'x' / Bytes(4)
        ),
        VerifyOrWriteChecksums
    )

    with pytest.raises(ChecksumCalcError):
        s.parse(test_data)
