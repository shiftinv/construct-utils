import os
from dataclasses import dataclass
from construct import \
    Construct, Subconstruct, ConstructError, SizeofError, Path, \
    stream_read, stream_write, evaluate, singleton
from typing import Any, Optional, List, Type

from .misc import \
    seek_temporary, get_offset_in_outer_stream, \
    get_root_stream, context_global


class DeferredError(ConstructError):
    pass


@dataclass
class DeferredMeta:
    '''
    Internal container class for keeping track of metadata for deferred fields

    Attributes:
        subcon (Subconstruct): Subconstruct of corresponding :class:`DeferredValue` instance
        path (str): Parsing/Building path of corresponding :class:`DeferredValue` instance
        target_offset (int): Target offset in outermost stream
        placeholder_data (bytes): Temporary placeholder bytes, used for sanity checks
        new_value (Any, optional): Final written value, only valid if :attr:`new_value_written` is True
        new_value_written (bool): True if a final value was written
    '''

    subcon: Subconstruct
    path: str
    target_offset: int
    placeholder_data: bytes
    new_value: Optional[Any] = None
    new_value_written: bool = False

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


class DeferredValue(Subconstruct):
    '''
    Subconstruct allowing for deferred writing of values in seekable streams.

    Initially, a placeholder value will be written in place of the actual subconstruct value,
    which should later be updated/finalized using :class:`WriteDeferredValue`.
    '''

    def __init__(self, subcon, meta_type: Type[DeferredMeta] = DeferredMeta):
        super().__init__(subcon)
        self.flagbuildnone = True  # no value has to be provided for building

        self.meta_type = meta_type

        try:
            self.placeholder_size = subcon.sizeof()
        except SizeofError as e:
            raise DeferredError('couldn\'t determine size of deferred field (must be constant)') from e

    def _build(self, obj, stream, context, path):
        # expect `None`, we're building a placeholder instead of a real value
        if obj is not None:
            raise DeferredError(f'building expected `None`, but got {obj}', path=path)

        # calculate current offset in outermost stream
        target_offset = get_offset_in_outer_stream(stream, context, path)

        # build placeholder value in place of real value
        placeholder_data = os.urandom(self.placeholder_size)
        stream_write(stream, placeholder_data, len(placeholder_data), path)

        # create and return `DeferredMeta` object, which is later used by `WriteDeferredValue`
        meta = self.meta_type(self.subcon, path, target_offset, placeholder_data)
        self._get_instances(context).append(meta)
        return meta

    @staticmethod
    def _get_instances(context) -> List[DeferredMeta]:
        return context_global(context, '_deferred_meta', [])


class WriteDeferredValue(Construct):
    '''
    Writes a provided value (or value of a provided expression) in place of
    a :class:`DeferredValue` at a given :attr:`path`
    '''

    def __init__(self, expr: Any, path: Path):
        super().__init__()
        self.expr = expr
        self.path = path

        self.flagbuildnone = True

    def _build(self, obj, stream, context, path):
        # evaluate path to `DeferredMeta` instance in context
        deferred = evaluate(self.path, context)
        if not isinstance(deferred, DeferredMeta):
            raise DeferredError('value is not an instance of DeferredMeta', path=path)
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
        for meta in DeferredValue._get_instances(context):
            if not meta.new_value_written:
                raise DeferredError(f'deferred value at \'{meta.path}\' was never written', path=path)

    def _sizeof(self, context, path):
        return 0
