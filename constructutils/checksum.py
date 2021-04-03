import hashlib
import functools
from construct import Subconstruct, Hex, Bytes
from typing import Callable


class ChecksumError(Exception):
    '''
    Error containing :attr:`expected` and :attr:`actual` hash values,
    raised on hash mismatches
    '''

    expected: bytes
    actual: bytes

    def __init__(self, message: str, expected: bytes, actual: bytes):
        super().__init__(message)
        self.expected = expected
        self.actual = actual

    def __str__(self):
        return f'{super().__str__()}\n  expected: {self.expected.hex()}\n  got:      {self.actual.hex()}'


class ChecksumValue:
    '''
    Represents an expected checksum value, which can be used to verify data with :func:`verify`
    '''

    expected: bytes

    def __init__(self, expected: bytes, func: Callable[[bytes], 'hashlib._Hash'], name: str):
        self.expected = expected
        self._func = func
        self._name = name

    def verify(self, data: bytes):
        '''
        Calculates the checksum for the given data,
        and raises and exception if the value does not match the expected checksum

        Args:
            data (bytes): Data to be verified

        Raises:
            ChecksumError: If checksum/digest of given data does not match expected value
        '''
        digest = self._func(data).digest()
        if self.expected != digest:
            raise ChecksumError('hash mismatch', self.expected, digest)

    def __repr__(self):
        return f'{type(self).__name__}[{self._name}, {self.expected.hex()}]'


class Checksum(Subconstruct):
    '''
    Parses checksum bytes into a :class:`ChecksumValue`, based on a :mod:`hashlib.*` method
    '''

    def __init__(self, func: Callable[[bytes], 'hashlib._Hash']):
        tmp = func(b'')
        super().__init__(Hex(Bytes(tmp.digest_size)))
        self._create_checksumvalue = functools.partial(ChecksumValue, func=func, name=tmp.name)  # type: Callable[[bytes], ChecksumValue]

    def _parse(self, stream, context, path):
        return self._create_checksumvalue(
            super()._parse(stream, context, path),
        )

    def _build(self, obj, stream, context, path):
        val = obj.expected if isinstance(obj, ChecksumValue) else obj
        return super()._build(val, stream, context, path)
