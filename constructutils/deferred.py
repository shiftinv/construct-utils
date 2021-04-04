import inspect
from dataclasses import dataclass
from construct import Construct, Subconstruct, Prefixed, ConstructError, SizeofError, Path, \
    stream_tell, stream_seek, stream_read, evaluate, singleton
from typing import Any, Optional, List

from .misc import seek_temporary, get_root_context, get_root_stream


class DeferredError(ConstructError):
    path: Optional[str]

    def __init__(self, message: str, path: Optional[str] = None):
        super().__init__(message, path)
        self.path = path

    def __str__(self):
        s = super().__str__()
        if self.path:
            s += f' [path: {self.path}]'
        return s


def _get_deferred_list(context) -> List['DeferredMeta']:
    '''
    Returns the global list of :class:`DeferredMeta` instances for the given context,
    creating it if it doesn't exist yet

    Returns:
        List[DeferredMeta]: List of :class:`DeferredMeta` instances for context
    '''
    root = get_root_context(context)
    val = getattr(root, '_deferred_list', None)
    if val is None:
        val = []
        setattr(root, '_deferred_list', val)
    return val


@dataclass
class DeferredMeta:
    '''
    Internal container class for keeping track of metadata for deferred fields

    Attributes:
        subcon (Subconstruct): Subconstruct of corresponding :class:`DeferredValue` instance
        path (str): Parsing/Building path of corresponding :class:`DeferredValue` instance
        target_offset (int): Target offset in outermost stream
        placeholder_data (bytes): Built value of placeholder, used for sanity checks
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

    def __init__(self, subcon, placeholder):
        super().__init__(subcon)
        try:
            subcon.sizeof()
        except SizeofError as e:
            raise DeferredError('couldn\'t determine size of deferred field (must be constant)') from e
        self.placeholder = placeholder
        self.flagbuildnone = True  # no value has to be provided for building

    # this is probably not reliable, but required for working around nested BytesIO calls
    def __get_offset_in_outer_stream(self, stream, context, path):
        offset = stream_tell(stream, path)

        # collect offsets of enclosing streams by walking up the tree
        def collect(context, prev_stream):
            nonlocal offset
            curr_stream = getattr(context, '_io', None)
            if curr_stream is not None:
                # add to offset if stream changed
                if curr_stream is not prev_stream:
                    offset += stream_tell(context._io, path)
                # continue to root recursively
                if hasattr(context, '_'):
                    collect(context._, curr_stream)
        collect(context, stream)

        # the Prefixed type writes the length _after_ building the subcon (which makes sense),
        #  but that also means that the current data will be written at [current offset] + [size of length field],
        #  which has to be taken into account as the stream's offset doesn't include the length field yet
        stack = inspect.stack()
        try:
            for info in stack:
                if info.function != '_build':
                    continue
                local_self = info.frame.f_locals.get('self')
                if isinstance(local_self, Prefixed):
                    offset += local_self.lengthfield.sizeof()
        finally:
            del stack  # just to be safe, see https://docs.python.org/3/library/inspect.html#the-interpreter-stack

        return offset

    def _build(self, obj, stream, context, path):
        # expect `None`, we're building a placeholder instead of a real value
        if obj is not None:
            raise DeferredError(f'building expected `None`, but got {obj}', path=path)

        # calculate current offset in outermost stream
        target_offset = self.__get_offset_in_outer_stream(stream, context, path)

        # build placeholder value in place of real value
        pre_offset = stream_tell(stream, path)
        self.subcon._build(self.placeholder, stream, context, path)
        post_offset = stream_tell(stream, path)

        # re-read written data for later comparison
        stream_seek(stream, pre_offset, 0, path)
        placeholder_data = stream_read(stream, post_offset - pre_offset, path)

        # create and return `DeferredMeta` object, which is later used by `WriteDeferredValue`
        meta = DeferredMeta(self.subcon, path, target_offset, placeholder_data)
        _get_deferred_list(context).append(meta)
        return meta


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
        lst = _get_deferred_list(context)
        for meta in lst:
            if not meta.new_value_written:
                raise DeferredError(f'deferred value at \'{meta.path}\' was never written', path=path)

    def _sizeof(self, context, path):
        return 0
