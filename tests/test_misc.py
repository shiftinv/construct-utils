import collections
from construct import Array, Byte
from constructutils import DictZipAdapter, AttributeRawCopy


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
