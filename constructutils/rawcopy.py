from construct import Struct, Array, RawCopy
from typing import Union


class AttributeRawCopy(RawCopy):
    '''
    Similar to :class:`RawCopy`, but instead of returning a dict `{'data': [bytes], 'value': [Any]}`
    it assigns the raw `data` to a property of `value` (`__raw__` by default, can be changed with `@`).

    Especially useful in combination with :class:`inline.InlineStruct`.

    Examples:
        >>> s = InliningStruct(
        ...     'val' / Byte,
        ...     'raw_data' @ AttributeRawCopy(InlineStruct(
        ...         'num' / Int16ul
        ...     ))
        ... )
        ...
        >>> c = s.parse(b'\\xff\\x00\\x02')
        >>> assert c.val == 0xff and c.num == 0x200
        >>> assert c.raw_data == b'\\x00\\x02'
    '''

    __raw_key = '__raw__'

    def __init__(self, subcon: Union[Struct, Array]):
        if not isinstance(subcon, (Struct, Array)):
            raise RuntimeError('AttributeRawCopy must contain `Struct` or `Array` instance')
        super().__init__(subcon)

    def _parse(self, stream, context, path):
        rc = super()._parse(stream, context, path)

        # store raw bytes in parsed data
        assert not hasattr(rc.value, self.__raw_key)  # just to be sure
        setattr(rc.value, self.__raw_key, rc.data)

        # return parsed data only
        return rc.value

    def _build(self, obj, stream, context, path):
        return super()._build({'value': obj}, stream, context, path)

    def __rmatmul__(self, name):
        self.__raw_key = name
        return self
