import inspect
import contextlib
import collections
from enum import Enum
from construct import \
    Adapter, Subconstruct, Container, ListContainer, Prefixed, Switch, ConstructError, MappingError, \
    stream_tell, stream_seek
from typing import Iterator, Union, List, Tuple, IO, Type

from .noemit import NoEmitMixin
from .rawcopy import RawCopyBytes


class DictZipAdapter(Adapter):
    '''
    Adapter for joining a predefined list of keys with a parsed list of values.

    Subconstruct must parse to a :class:`ListContainer`, e.g. :class:`Array` or :class:`Sequence`;
    build input must be an :class:`OrderedDict`.
    '''

    def __init__(self, keys: Union[List, Tuple], subcon):
        super().__init__(subcon)
        self.keys = keys

    def _decode(self, obj: ListContainer, context, path):
        assert isinstance(obj, ListContainer)

        assert len(self.keys) == len(obj)
        container = Container(zip(self.keys, obj))

        # copy attributes set by :class:`AttributeRawCopy`
        for k, v in obj.__dict__.items():
            if isinstance(v, RawCopyBytes):
                setattr(container, k, v)

        return container

    def _encode(self, obj: dict, context, path):
        assert isinstance(obj, collections.OrderedDict)
        return obj.values()


class EnumConvert(Subconstruct):
    '''
    Similar to :class:`construct.Enum`, but more restrictive regarding the input/output types.

    Parsing and building will both return an instance of the provided enum type
    (cf. :class:`construct.Enum`, where building will return the built subcon value instead of the enum value)
    '''

    def __init__(self, subcon, enum: Type[Enum]):
        if not issubclass(enum, Enum):
            raise MappingError(f'enum parameter must be of type `Enum` (not {type(enum).__name__})')
        super().__init__(subcon)

        self.enum = enum
        mapping = [(e, e.value) for e in self.enum]
        self.encmapping = dict(mapping)
        self.decmapping = dict((m[1], m[0]) for m in mapping)

    def _parse(self, stream, context, path):
        obj = super()._parse(stream, context, path)
        try:
            return self.decmapping[obj]
        except KeyError:
            raise MappingError(f'no `{self.enum.__name__}` mapping for value {obj!r}', path=path)

    def _build(self, obj, stream, context, path):
        if not isinstance(obj, self.enum):
            raise MappingError(f'expected `{self.enum.__name__}` value, got {obj!r}', path=path)
        super()._build(obj.value, stream, context, path)
        return obj


#####
# switch stuff
#####

class SwitchKeyError(ConstructError):
    pass


class _DictNoDefault(dict):
    def get(self, key, default=None):
        try:
            # drop default parameter
            return self[key]
        except KeyError:
            raise SwitchKeyError(f'unknown key for switch: {key!r}')


class SwitchNoDefault(NoEmitMixin, Switch):
    '''
    Similar to :class:`Switch`, but does not pass successfully if no case matches
    '''

    # (it's not pretty, but it's the easiest solution without having to copy and modify the code)
    def __init__(self, keyfunc, cases):
        # patch case dictionary to drop default parameter
        super().__init__(keyfunc, _DictNoDefault(cases))

    def _parse(self, stream, context, path):
        try:
            return super()._parse(stream, context, path)
        except SwitchKeyError as e:
            # re-raise error with path
            raise SwitchKeyError(e.args[0], path=path)

    def _build(self, obj, stream, context, path):
        try:
            return super()._build(obj, stream, context, path)
        except SwitchKeyError as e:
            # re-raise error with path
            raise SwitchKeyError(e.args[0], path=path)


#####
# stream stuff
#####

@contextlib.contextmanager
def seek_temporary(stream: IO, path: str, offset: int):
    '''
    Context manager which seeks to the specified offset on entering,
    and seeks back to the original offset on exit
    '''
    fallback = stream_tell(stream, path)
    stream_seek(stream, offset, 0, path)
    yield
    stream_seek(stream, fallback, 0, path)


def get_offset_in_outer_stream(stream, context, path):
    '''
    Tries to calculate the current offset in the outermost stream by traversing the context tree.

    This is very likely to go completely wrong in many configurations;
    right now it takes streams in other contexts and the :class:`Prefixed` type into account.
    '''
    offset = stream_tell(stream, path)

    # collect offsets of enclosing streams by walking up the tree
    prev_stream = stream
    for c in iter_context_tree(context):
        curr_stream = getattr(c, '_io', None)
        if curr_stream is None:
            break

        # add to offset if stream changed
        if curr_stream is not prev_stream:
            offset += stream_tell(curr_stream, path)
        prev_stream = curr_stream

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


#####
# context stuff
#####

def iter_context_tree(context: Container) -> Iterator[Container]:
    yield context

    # walk up the tree until no new parent (`_`) exists
    while True:
        next_parent = getattr(context, '_', context)
        if next_parent is context:  # either no `_` attribute, or self-reference
            break
        context = next_parent
        yield context
    return context


def get_root_context(context: Container) -> Container:
    '''
    Returns the topmost/root context relative to a provided context
    '''
    *_, root = iter_context_tree(context)
    return root


def get_root_stream(context: Container) -> IO:
    '''
    Returns the outermost IO/stream relative to a provided context
    '''
    top_io = None
    for c in iter_context_tree(context):
        top_io = getattr(c, '_io', top_io)
    assert top_io is not None
    return top_io


def context_global(context, name: str, default):
    '''
    Returns a context-global value, creating it if it doesn't exist yet
    '''
    root = get_root_context(context)

    if hasattr(root, name):
        val = getattr(root, name)
    else:
        val = default
        setattr(root, name, val)

    return val
