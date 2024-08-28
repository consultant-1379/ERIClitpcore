class BakedQueryResultWrapper(object):
    def __init__(self, iterator):
        self._iterator = iterator

    def __iter__(self):
        return self._iterator.__iter__()

    def __getitem__(self, key):
        return list(self._iterator)[key]
