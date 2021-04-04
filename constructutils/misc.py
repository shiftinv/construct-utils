import contextlib
import collections
from construct import \
    Adapter, Container, \
    stream_tell, stream_seek
from typing import Iterator, Union, List, Tuple, IO

from .rawcopy import RawCopyBytes


class DictZipAdapter(Adapter):
    def __init__(self, keys: Union[List, Tuple], subcon):
        super().__init__(subcon)
        self.keys = keys

    def _decode(self, obj: list, context, path):
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
