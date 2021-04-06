import io
import functools
import construct


__orig_attr = '__io_patched_orig__'


def patch():
    '''
    monkey-patches `construct.Struct._parse` to clean up leftover `_io` attributes after parsing,
    which would create issues when building :class:`DeferredValue` instances (or derived types) later on

    See https://github.com/construct/construct/blob/96e0960caa3e26cb058d8d22aa2d2bfefb9c211f/construct/core.py#L2115
    '''

    orig = construct.Struct._parse
    if hasattr(orig, __orig_attr):
        # already patched
        return

    @functools.wraps(orig)
    def patched(*args, **kwargs):
        obj = orig(*args, **kwargs)
        if '_io' in obj and isinstance(obj['_io'], io.IOBase):
            del obj['_io']
        return obj
    setattr(patched, __orig_attr, orig)

    construct.Struct._parse = patched


def unpatch():
    '''
    Undoes :meth:`patch`
    '''
    construct.Struct._parse = getattr(construct.Struct._parse, __orig_attr)
