import pytest
import hashlib
from constructutils import Checksum, ChecksumValue, ChecksumError


def test_size():
    assert Checksum(hashlib.sha1).sizeof() == 20
    assert Checksum(hashlib.sha256).sizeof() == 32


def test_parse():
    c = Checksum(hashlib.sha1)
    v = bytes(range(20))
    assert c.parse(v).expected == v


def test_build():
    c = Checksum(hashlib.sha1)
    v = bytes(range(20))
    assert c.build(v) == v
    assert c.build(ChecksumValue(v, hashlib.sha1, 'sha1')) == v


def test_verify():
    data = b'test'
    digest = hashlib.sha1(data).digest()
    cv = ChecksumValue(digest, hashlib.sha1, 'sha1')

    # valid data, make sure no exception is raised
    cv.verify(data)

    # invalid data
    data2 = data + b'x'
    with pytest.raises(ChecksumError) as e:
        cv.verify(data2)
    assert e.value.expected == digest
    assert e.value.actual == hashlib.sha1(data2).digest()
