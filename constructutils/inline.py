from construct import Struct, Subconstruct, ConstructError
from construct.core import Construct

from .noemit import NoEmitMixin


class InlineError(ConstructError):
    pass


class InliningStruct(NoEmitMixin, Struct):
    '''
    Similar to a standard :class:`Struct`,
    but inlines properties of :class:`Inline`/:class:`InlineStruct` descendants into itself
    (i.e. flattens nested instances).

    This is mainly useful for wrapping :class:`Struct`s in context-modifying subconstructs
    that pass through the resulting value.

    Does not have any use on its own, only in conjunction with :class:`Inline`/:class:`InlineStruct` instances.

    Examples:
        >>> s = InliningStruct(
        ...     'val' / Byte,
        ...     InlineStruct(
        ...         'inner' / Byte
        ...     )
        ... )
        ...
        >>> c = s.parse(b'\\x00\\xff')
        >>> assert c.val == 0x00
        >>> assert c.inner == 0xff
    '''

    __tag = 0

    def __init__(self, *subcons, **subconskw):
        super().__init__(*subcons, **subconskw)

        # look for _InlineMixin subcons, traverse Subconstruct instances
        self.__inline = []
        for s in self.subcons:
            if _InlineMixin._is_inline(s):
                self.__inline.append(s)

        # prevent collisions between nested instances with global counter/tag
        cls = type(self)
        tag = cls.__tag
        cls.__tag += 1

        for i, s in enumerate(self.__inline):
            s.name = f'__inline_{tag}_{i}'

    # try own attributes first, then delegate to inlined structs
    def __getattr__(self, name):
        for s in (super(), *self.__inline):
            try:
                return s.__getattr__(name)
            except AttributeError:
                pass
        raise AttributeError

    # parse struct normally, then move elements of nested structs into current object
    def _parse(self, stream, context, path):
        context._is_inline = True
        obj = super()._parse(stream, context, path)
        for s in self.__inline:
            # remove nested struct
            subobj = obj.pop(s.name)
            # insert parsed values into outer object
            obj.update(subobj)
        return obj

    def _build(self, obj, stream, context, path):
        if obj is not None:
            # put entire input object for each inlined struct as the inlined subcons are not known
            for s in self.__inline:
                obj[s.name] = obj

        context._is_inline = True
        subcontext = super()._build(obj, stream, context, path)
        # inlined structs already inserted their data into the outer context, only cleanup nested structs now
        for s in self.__inline:
            obj.pop(s.name)
            subcontext.pop(s.name)

        return subcontext


class _InlineMixin:
    '''
    Used within an :class:`InliningStruct` for inlining nested properties.
    '''

    def _parse(self, stream, context, path):
        self.__check_inline(context, path)
        obj = super()._parse(stream, context, path)  # type: ignore
        # insert parsed data into outer context
        context.update(obj)
        return obj

    def _build(self, obj, stream, context, path):
        self.__check_inline(context, path)
        subcontext = super()._build(obj, stream, context, path)  # type: ignore
        # insert built data into outer context
        context.update(subcontext)
        return subcontext

    @classmethod
    def __check_inline(cls, context, path):
        if not context._.get('_is_inline', False):
            raise InlineError(f'`{cls.__name__}`s may only be part of `InliningStruct`s', path=path)

    @staticmethod
    def _is_inline(construct: Construct) -> bool:
        '''
        Returns True if the provided construct or any of its
        subconstructs (recursively, where applicable) is an :class:`InlineStruct`
        '''
        _c = construct
        while True:
            if isinstance(_c, _InlineMixin):
                # found
                return True
            if not isinstance(_c, Subconstruct):
                # not a subconstruct
                break
            # step
            _c = _c.subcon
        return False


class Inline(_InlineMixin, Subconstruct):
    '''
    Used within an :class:`InliningStruct` for inlining nested properties.
    '''


class InlineStruct(_InlineMixin, InliningStruct):
    '''
    Similar to a standard :class:`Struct`,
    used together with :class:`InliningStruct` for inlining nested properties.

    Also acts as an :class:`InliningStruct` itself to allow for easy nesting.
    '''
