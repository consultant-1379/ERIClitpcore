from litp.core.plugin import Plugin


class _BasePlugin(Plugin):
    def __cmp__(self, other):
        if self.__class__ is other.__class__:
            return 0
        else:
            return -1

class CPlugin(_BasePlugin):
    pass
