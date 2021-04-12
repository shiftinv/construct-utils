import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from construct import \
    Construct, Subconstruct, ConstructError, SizeofError, Path, Container, \
    stream_read, stream_write, evaluate, singleton
from typing import Any, Generic, Optional, List, Type, TypeVar, Union, cast

from .misc import \
    seek_temporary, get_offset_in_outer_stream, \
    get_root_stream, context_global


class DeferredError(ConstructError):
    pass


@dataclass
class DeferredMetaBase:
    '''
    Internal container class for keeping track of metadata for deferred fields

    Attributes:
        path (str): Parsing/Building path of associated instance
    '''

    path: str


@dataclass
class DeferredParseMeta(DeferredMetaBase):
    '''
    Internal container class for keeping track of metadata for deferred fields while parsing

    Attributes:
        value (Any): Parsed value of associated instance
    '''

    value: Any


@dataclass
class DeferredBuildMeta(DeferredMetaBase):
    '''
    Internal container class for keeping track of metadata for deferred fields while building

    Attributes:
        subcon (Subconstruct): Subconstruct of associated :class:`DeferredValue` instance
        target_offset (int): Target offset in outermost stream
        placeholder_data (bytes): Temporary placeholder bytes, used for sanity checks
        new_value (Any, optional): Final written value, only valid if :attr:`new_value_written` is True
        new_value_written (bool): True if a final value was written
    '''

    subcon: Subconstruct
    target_offset: int
    placeholder_data: bytes
    new_value: Optional[Any] = field(default=None, init=False)
    new_value_written: bool = field(default=False, init=False)

    def _build_value(self, obj, stream, context, path):
        '''
        Builds stored :attr:`subcon` with given parameters, overwriting placeholder data
        '''
        assert not self.new_value_written
        with seek_temporary(stream, path, self.target_offset):
            self.new_value = self.subcon._build(obj, stream, context, path)
        self.new_value_written = True

    def _check_placeholder(self, stream, path):
        '''
        Does a sanity check by comparing the data at the target location with the expected placeholder
        '''
        # seek to target offset, check if data matches originally written placeholder data
        with seek_temporary(stream, path, self.target_offset):
            read_data = stream_read(stream, len(self.placeholder_data), path)
        if read_data != self.placeholder_data:
            raise DeferredError(f'something went wrong, data at target location ({read_data.hex()}) does not equal expected placeholder data ({self.placeholder_data.hex()})', path=path)


_TMetaParse = TypeVar('_TMetaParse', bound=DeferredParseMeta)
_TMetaBuild = TypeVar('_TMetaBuild', bound=DeferredBuildMeta)


class DeferredValueBase(ABC, Generic[_TMetaParse, _TMetaBuild], Subconstruct):
    '''
    Subconstruct allowing for deferred writing of values in seekable streams.

    Initially, a placeholder value will be written in place of the actual subconstruct value,
    which should later be updated/finalized using :class:`WriteDeferredValue`.
    '''

    def __init__(self, subcon):
        super().__init__(subcon)
        self.flagbuildnone = True  # no value has to be provided for building

        try:
            self.placeholder_size = subcon.sizeof()
        except SizeofError as e:
            raise DeferredError('couldn\'t determine size of deferred field (must be constant)') from e

    def _parse(self, stream, context, path):
        value = super()._parse(stream, context, path)
        # create meta object, but return parsed value
        # doesn't do anything on its own in this case, but can be extended by subclasses
        self._create_global_meta(context, path, value)
        return value

    def _build(self, obj, stream, context, path):
        # expect `None`, we're building a placeholder instead of a real value
        if obj is not None:
            raise DeferredError(f'building expected `None`, but got {obj}', path=path)

        # calculate current offset in outermost stream
        target_offset = get_offset_in_outer_stream(stream, context, path)

        # build placeholder value in place of real value
        placeholder_data = os.urandom(self.placeholder_size)
        stream_write(stream, placeholder_data, len(placeholder_data), path)

        # create and return meta object, which can later be used by `WriteDeferredValue`
        return self._create_global_meta(context, path, self.subcon, target_offset, placeholder_data)

    @classmethod
    def _get_instances(cls, context: Container) -> Union[List[_TMetaParse], List[_TMetaBuild]]:
        '''
        Returns context-global list of metadata instances
        '''
        return context_global(context, cls._get_meta_name(), cast(Any, []))

    def _create_global_meta(self, context: Container, path: str, *args: Any) -> Union[_TMetaParse, _TMetaBuild]:
        '''
        Creates a new metadata instance with the provided parameters and adds it to the global list
        '''
        meta_type = self._get_meta_type(context._building)
        meta = meta_type(path, *args)

        global_list = cast(List[DeferredMetaBase], self._get_instances(context))
        global_list.append(meta)
        return meta

    def _get_meta_type(self, is_building: bool) -> Type[Union[_TMetaParse, _TMetaBuild]]:
        '''
        Returns the correct generic metadata parameter type for building/parsing
        '''
        bases = type(self).__orig_bases__
        args = next(b.__args__ for b in bases if b.__origin__ is DeferredValueBase)
        return args[1] if is_building else args[0]

    @staticmethod
    @abstractmethod
    def _get_meta_name() -> str:
        '''
        Returns the name of the context-global list of metadata instances
        '''
        pass


class DeferredValue(DeferredValueBase[DeferredParseMeta, DeferredBuildMeta]):
    @staticmethod
    def _get_meta_name() -> str:
        return '_deferred_meta'


class WriteDeferredValue(Construct):
    '''
    Writes a provided value (or value of a provided expression) in place of
    a :class:`DeferredValue` at a given path
    '''

    def __init__(self, expr: Any, meta: Union[Path, DeferredBuildMeta]):
        super().__init__()
        self.expr = expr
        self.meta = meta

        self.flagbuildnone = True

    def _build(self, obj, stream, context, path):
        # evaluate path to `DeferredBuildMeta` instance in context
        deferred = evaluate(self.meta, context)
        if not isinstance(deferred, DeferredBuildMeta):
            raise DeferredError('value is not an instance of DeferredBuildMeta', path=path)
        new_value = evaluate(self.expr, context)

        # use outer stream for writing
        outer_stream = get_root_stream(context)

        # sanity check placeholder, then build/write new value
        deferred._check_placeholder(outer_stream, path)
        deferred._build_value(new_value, outer_stream, context, path)

    def _parse(self, stream, context, path):
        pass

    def _sizeof(self, context, path):
        return 0


@singleton
class CheckDeferredValues(Construct):
    '''
    Ensures that all :class:`DeferredValue` instances in the current context have been
    written to (using :class:`WriteDeferredValue`); raises an exception at build-time
    if a value was not written
    '''

    def __init__(self):
        super().__init__()
        self.flagbuildnone = True

    def _parse(self, stream, context, path):
        pass

    def _build(self, obj, stream, context, path):
        for meta in cast(List[DeferredBuildMeta], DeferredValue._get_instances(context)):
            if not meta.new_value_written:
                raise DeferredError(f'deferred value at \'{meta.path}\' was never written', path=path)

    def _sizeof(self, context, path):
        return 0
