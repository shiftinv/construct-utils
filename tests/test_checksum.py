import pytest
import hashlib
from construct import Struct, Bytes, Array, Byte, this

from constructutils import \
    ChecksumCalcError, ChecksumVerifyError, \
    ChecksumRaw, ChecksumValue, ChecksumSourceData, VerifyOrWriteChecksums


test_struct = Struct(
    'hash' / ChecksumValue(hashlib.sha1, this.data),
    'data' / ChecksumSourceData(Struct(
        'x' / Bytes(4)
    )),
    VerifyOrWriteChecksums
)
test_data = hashlib.sha1(b'test').digest() + b'test'
test_data_invalid = b'\x00' + test_data[1:]


def test_raw():
    assert ChecksumRaw(hashlib.sha1).sizeof() == 20


def test_parse_valid():
    assert test_struct.parse(test_data) == {
        'hash': test_data[:-4],
        'data': {'x': b'test'}
    }


def test_parse_invalid():
    with pytest.raises(ChecksumVerifyError) as e:
        test_struct.parse(test_data_invalid)
    assert e.value.expected == test_data_invalid[:-4]
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


def test_list():
    s = Struct(
        ChecksumValue(hashlib.sha1, lambda this: this.data[0:2], True),
        'data' / Array(3, ChecksumSourceData(Struct(
            'a' / Byte
        ))),
        VerifyOrWriteChecksums
    )

    values = b'\x01\x02\x03'

    # same range
    hashval = hashlib.sha1(values[0:2]).digest()
    assert s.parse(hashval + values) == {'data': [{'a': 1}, {'a': 2}, {'a': 3}]}

    # different range
    hashval = hashlib.sha1(values[0:1]).digest()
    with pytest.raises(ChecksumVerifyError):
        s.parse(hashval + values)


def test_list_invalid():
    s = Struct(
        'hash' / ChecksumValue(hashlib.sha1, this.data, True),  # note: True instead of default False
        'data' / ChecksumSourceData(Struct(
            'x' / Bytes(4)
        )),
        VerifyOrWriteChecksums
    )

    with pytest.raises(ChecksumCalcError):
        s.parse(test_data)


def test_skip():
    # no exception should be raised even though the checksum doesn't match
    test_struct.parse(test_data_invalid, skip_verify_checksums=True)
