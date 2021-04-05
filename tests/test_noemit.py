from construct import Bytes

from constructutils.noemit import NoEmitMixin


def test():
    class NoEmitBytes(NoEmitMixin, Bytes):
        pass

    # should compile custom code
    inst = Bytes(2)
    assert str(id(inst)) not in inst.compile().source

    # should fall back to linked instance
    inst = NoEmitBytes(2)
    assert str(id(inst)) in inst.compile().source
