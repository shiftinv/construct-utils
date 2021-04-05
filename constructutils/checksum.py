import hashlib
from dataclasses import dataclass
from construct import \
    Hex, Bytes, Construct, Subconstruct, Container, \
    ConstructError, evaluate, singleton
from typing import Any, Callable, List, Type, TypeVar, Union, cast

from .deferred import DeferredParseMeta, DeferredBuildMeta, DeferredValueBase, WriteDeferredValue
from .rawcopy import AttributeRawCopy


HashFunc = Callable[[bytes], 'hashlib._Hash']
DataExprValue = Union[bytes, List[bytes], Container, List[Container]]
DataExpr = Union[DataExprValue, Callable[[Any], DataExprValue]]

CHECKSUM_RAW_DATA_NAME = '__checksum_raw_data__'


class ChecksumCalcError(ConstructError):
    '''
    Error raised on checksum calculation failure
    '''


class ChecksumVerifyError(Exception):
    '''
    Error containing :attr:`expected` and :attr:`actual` hash values,
    raised on hash mismatches
    '''

    expected: bytes
    actual: bytes

    def __init__(self, message: str, expected: bytes, actual: bytes, *args):
        super().__init__(message, expected, actual, *args)
        self.expected = expected
        self.actual = actual

    def __str__(self):
        return f'{super().__str__()}\n  expected: {self.expected.hex()}\n  got:      {self.actual.hex()}'


class ChecksumRawValue(bytes):
    hash_name: str
    verified: bool = False


class ChecksumRaw(Subconstruct):
    '''
    Parses and builds bytes based on a `hashlib.*` method;
    parsed value is a :class:`ChecksumRawValue`, which represents the checksum bytes
    '''

    def __init__(self, hash_func: HashFunc):
        h = hash_func(b'')
        super().__init__(Hex(Bytes(h.digest_size)))
        self.hash_name = h.name

    def _parse(self, stream, context, path):
        v = ChecksumRawValue(super()._parse(stream, context, path))
        v.hash_name = self.hash_name
        return v


@dataclass
class ChecksumValueMeta:
    '''
    Mixin for use with :class:`DeferredMetaBase`,
    holds properties related to checksum calculation/validation
    '''

    hash_func: HashFunc
    data_expr: DataExpr
    data_expr_context: Container
    data_expr_is_list: bool


@dataclass
class ChecksumValueParseMeta(ChecksumValueMeta, DeferredParseMeta):
    '''
    Internal container class
    '''
    pass


@dataclass
class ChecksumValueBuildMeta(ChecksumValueMeta, DeferredBuildMeta):
    '''
    Internal container class
    '''
    pass


class ChecksumValue(DeferredValueBase[ChecksumValueParseMeta, ChecksumValueBuildMeta]):
    '''
    Subconstruct for checksum value.

    :class:`VerifyOrWriteChecksums` can be used to verify data
    (see :class:`ChecksumSourceData`) using this checksum when parsing,
    or replace/update this value with the checksum of the specified data.

    Examples:
        >>> s = Struct(
        ...     'hash' / ChecksumValue(hashlib.sha1, this.data),
        ...     'struct' / ChecksumSourceData(Struct(
        ...         'inner' / Bytes(2)
        ...     )),
        ...     VerifyOrWriteChecksums
        ... )
        ...
        >>> inner = b'01'
        >>> hashval = hashlib.sha1(inner).digest()
        >>>
        >>> # calculates checksum
        >>> data = s.build({'struct': {'x': inner}})
        >>> assert data[0:20] == hashval
        >>>
        >>> # raises exception on invalid checksum
        >>> with pytest.raises(ChecksumCalcError):
        ...     s.parse(hashval[:-1] + b'X' + inner)
    '''

    def __init__(self, hash_func: HashFunc, data_expr: DataExpr, data_expr_is_list: bool = False):
        super().__init__(ChecksumRaw(hash_func))

        self.hash_func = hash_func
        self.data_expr = data_expr
        self.data_expr_is_list = data_expr_is_list

    def _create_global_meta(self, context, path, *args):
        m = super()._create_global_meta(
            context, path, *args,
            self.hash_func, self.data_expr, context, self.data_expr_is_list
        )
        return m

    @staticmethod
    def _get_meta_name() -> str:
        return '_checksum_meta'


class ChecksumSourceData(AttributeRawCopy):
    '''
    Wrapper for source data used for building/verifying checksums
    '''

    def __init__(self, subcon):
        super().__init__(subcon, CHECKSUM_RAW_DATA_NAME)


_TMeta = TypeVar('_TMeta', bound=ChecksumValueMeta)


@singleton
class VerifyOrWriteChecksums(Construct):
    '''
    Verifies (when parsing) or calculates/writes (when building) checksums for :class:`ChecksumValue` instances
    '''

    def __init__(self):
        super().__init__()
        self.flagbuildnone = True

    def _parse(self, stream, context, path):
        for meta, hash_value in self.__iter_values(context, path, ChecksumValueParseMeta):
            # compare read/expected value with calculated value
            if meta.value != hash_value:
                raise ChecksumVerifyError(f'hash mismatch for path \'{meta.path}\'', meta.value, hash_value)
            else:
                meta.value.verified = True

    def _build(self, obj, stream, context, path):
        for meta, hash_value in self.__iter_values(context, path, ChecksumValueBuildMeta):
            # (ab)use WriteDeferredValue to overwrite the hash placeholder with the calculated value
            WriteDeferredValue(hash_value, meta)._build(None, stream, context, path)

    def _sizeof(self, context, path):
        return 0

    def __iter_values(self, context, path, _: Type[_TMeta]):
        for meta in ChecksumValue._get_instances(context):
            # evaluate data expression
            data_container = evaluate(meta.data_expr, meta.data_expr_context)
            if meta.data_expr_is_list:
                if type(data_container) != list:  # check type directly instead of `isinstance`, as `ListContainer` inherits from `list`
                    raise ChecksumCalcError(
                        f'expected data expression for ChecksumValue at \'{meta.path}\' to be a list, got {type(data_container).__name__}'
                    )
                data = b''.join(self.__get_raw_data(v, path, meta.path) for v in data_container)
            else:
                data = self.__get_raw_data(data_container, path, meta.path)

            # calculate checksum
            hash_value = meta.hash_func(data)  # type: ignore  # https://github.com/python/mypy/issues/5485

            yield cast(_TMeta, meta), hash_value.digest()

    @staticmethod
    def __get_raw_data(value, path, meta_path):
        try:
            return value if isinstance(value, bytes) else getattr(value, CHECKSUM_RAW_DATA_NAME)
        except AttributeError:
            raise ChecksumCalcError(
                f'data expression for ChecksumValue at \'{meta_path}\' does not contain raw data, make sure to use wrap the target in `ChecksumSourceData`',
                path=path
            )
