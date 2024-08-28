from litp.core import scope


class BaseManager(object):
    def __init__(self):
        self._data_manager = None

    @property
    def data_manager(self):
        if self._data_manager:
            return self._data_manager
        return scope.data_manager

    @data_manager.setter
    def data_manager(self, value):
        self._data_manager = value
