class NoEmitMixin:
    '''
    Mixin that raises a :class:`NotImplementedError` for `Construct._emit*` functions
    '''

    def _emitparse(*args, **kwargs):
        raise NotImplementedError

    def _emitbuild(*args, **kwargs):
        raise NotImplementedError

    def _emitseq(*args, **kwargs):
        raise NotImplementedError

    def _emitprimitivetype(*args, **kwargs):
        raise NotImplementedError

    def _emitfulltype(*args, **kwargs):
        raise NotImplementedError
