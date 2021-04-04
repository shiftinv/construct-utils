import collections
from construct import Adapter, Container
from typing import Union, List, Tuple

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
