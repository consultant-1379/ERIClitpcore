from litp.extensions.core_extension import ModelExtension


class _BaseExtension(ModelExtension):
    def __cmp__(self, other):
        if self.__class__ is other.__class__:
            return 0
        else:
            return -1

class AExtension(_BaseExtension):
    pass
