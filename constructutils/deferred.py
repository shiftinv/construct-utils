import inspect
from dataclasses import dataclass
from construct import Construct, Subconstruct, Prefixed, ConstructError, SizeofError, \
    stream_tell, stream_seek, stream_read, evaluate, singleton
from typing import Any, Optional, List


##################################################
# this code is taken from an older private project,
# is largely untested and contains a bunch of hacks.
# it should hence only be used for reference
##################################################


class DeferredError(ConstructError):
    pass


def _get_deferred_list(context) -> List['DeferredMeta']:
    val = getattr(context._root, '_deferred_list', None)
    if val is None:
        val = []
        setattr(context._root, '_deferred_list', val)
    return val


@dataclass
class DeferredMeta:
    subcon: Subconstruct
    path: str
    target_offset: int
    placeholder_data: Any
    new_value: Optional[Any] = None
    did_write_value: bool = False

    # called by WriteDeferredValue._build
    def _write_value(self, obj, outer_stream, context, path):
        self.new_value = self.subcon._build(obj, outer_stream, context, path)
        self.did_write_value = True

    def __eq__(self, other):
        if not self.did_write_value:
            raise DeferredError('cannot compare uninitialized deferred value')
        # support comparisons of two DeferredMeta objects
        if isinstance(other, DeferredMeta):
            if not other.did_write_value:
                raise DeferredError('other deferred value is uninitialized')
            other = other.new_value

        if not isinstance(other, type(self.new_value)):
            raise DeferredError(f'cannot compare incompatible types: {type(self.new_value)} and {type(other)}')
        return other == self.new_value


class DeferredValue(Subconstruct):
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
            if context._io is not prev_stream:
                offset += stream_tell(context._io, path)
            if getattr(context._, '_io', None):
                collect(context._, context._io)
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
        if obj not in (None, self.placeholder):
            raise DeferredError(f'building expected None or {self.placeholder} but got {obj}', path=path)
        target_offset = self.__get_offset_in_outer_stream(stream, context, path)

        pre_offset = stream_tell(stream, path)
        self.subcon._build(self.placeholder, stream, context, path)
        post_offset = stream_tell(stream, path)

        # re-read written data for later comparison
        stream_seek(stream, pre_offset, 0, path)
        placeholder_data = stream_read(stream, post_offset - pre_offset, path)

        meta = DeferredMeta(self.subcon, path, target_offset, placeholder_data)
        _get_deferred_list(context).append(meta)
        return meta


class WriteDeferredValue(Construct):
    SHOW_UNREADABLE_WARNING = True

    def __init__(self, subcon, path):
        super().__init__()
        self.subcon = subcon
        self.path = path
        self.flagbuildnone = True

    def _parse(self, stream, context, path):
        pass

    def _build(self, obj, stream, context, path):
        deferred = evaluate(self.path, context)
        if not isinstance(deferred, DeferredMeta):
            raise DeferredError('value is not an instance of DeferredMeta', path=path)
        new_value = evaluate(self.subcon, context)

        # use outer stream for writing
        stream = context._root._io

        fallback = stream_tell(stream, path)

        if stream.readable():
            stream_seek(stream, deferred.target_offset, 0, path)
            orig_data = stream_read(stream, len(deferred.placeholder_data), path)
            if orig_data != deferred.placeholder_data:
                raise DeferredError(f'something went wrong, data at target location ({orig_data}) does not equal placeholder data ({deferred.placeholder_data})')
        elif self.SHOW_UNREADABLE_WARNING and getattr(context._root, 'show_unreadable_warning', True):
            print('[warning] stream is not readable, cannot verify offset/placeholder value')
            setattr(context._root, 'show_unreadable_warning', False)

        stream_seek(stream, deferred.target_offset, 0, path)
        deferred._write_value(new_value, stream, context, path)
        stream_seek(stream, fallback, 0, path)

    def _sizeof(self, context, path):
        return 0


@singleton
class CheckDeferredValues(Construct):
    def __init__(self):
        super().__init__()
        self.flagbuildnone = True

    def _parse(self, stream, context, path):
        pass

    def _build(self, obj, stream, context, path):
        lst = _get_deferred_list(context)
        for meta in lst:
            if not meta.did_write_value:
                raise DeferredError(f'deferred value at \'{meta.path}\' was never written', path=path)

    def _sizeof(self, context, path):
        return 0
