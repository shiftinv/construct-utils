from construct import Struct, Array, RawCopy
from typing import Optional, Union, overload


class RawCopyError(Exception):
    pass


class AttributeRawCopy(RawCopy):
    '''
    Similar to :class:`RawCopy`, but instead of returning a dict `{'data': [bytes], 'value': [Any]}`
    it assigns the raw `data` to a property of `value` (`__raw__` by default, can be changed with `@` or using the parameters).

    Especially useful in combination with :class:`inline.InlineStruct`.

    Examples:
        >>> s = InliningStruct(
        ...     'val' / Byte,
        ...     'raw_data' @ AttributeRawCopy(InlineStruct(
        ...         'num' / Int16ul
        ...     )),
        ...     'array' / AttributeRawCopy(Array(3, Byte))
        ... )
        ...
        >>> c = s.parse(b'\\xff\\x00\\x02\\x0a\\x0b\\x0c')
        >>> assert c.val == 0xff and c.num == 0x200 and c.array == [10, 11, 12]
        >>> assert c.raw_data == b'\\x00\\x02'
        >>> assert c.array.__raw__ == b'\\x0a\\x0b\\x0c'
    '''

    __raw_key = '__raw__'

    def __init__(self, subcon: Union[Struct, Array], raw_key: Optional[str] = None):
        if not isinstance(subcon, (Struct, Array)):
            raise RawCopyError('AttributeRawCopy must contain `Struct` or `Array` instance')
        super().__init__(subcon)

        if raw_key is not None:
            self.__raw_key = raw_key

    def _parse(self, stream, context, path):
        rc = super()._parse(stream, context, path)

        # store raw bytes in parsed data
        if hasattr(rc.value, self.__raw_key):
            raise RawCopyError(f'context already has a \'{self.__raw_key}\' attribute')
        setattr(rc.value, self.__raw_key, rc.data)

        # return parsed data only
        return rc.value

    def _build(self, obj, stream, context, path):
        return super()._build({'value': obj}, stream, context, path)

    def __rmatmul__(self, name):
        return type(self)(self.subcon, name)
