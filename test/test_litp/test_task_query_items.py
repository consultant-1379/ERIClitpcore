import unittest

from litp.core.task_query_items import TaskQueryItems


class MockQueryItem(object):
    def __init__(self, vpath):
        self.vpath = vpath


class TestTaskQueryItems(unittest.TestCase):
    def test_init(self):
        shadow = set()
        item = MockQueryItem("/foo")

        obj = TaskQueryItems(lambda: shadow, set([item]))
        self.assertEquals(set([item]), obj)
        self.assertEquals(set([item.vpath]), shadow)

    def test_add(self):
        shadow = set()
        obj = TaskQueryItems(lambda: shadow)

        item = MockQueryItem("/foo")
        obj.add(item)
        self.assertEquals(set([item]), obj)
        self.assertEquals(set([item.vpath]), shadow)

    def test_remove(self):
        shadow = set()
        obj = TaskQueryItems(lambda: shadow)

        item = MockQueryItem("/foo")
        obj.add(item)
        obj.remove(item)
        self.assertEquals(set([]), obj)
        self.assertEquals(set([]), shadow)

    def test_update(self):
        shadow = set()
        obj = TaskQueryItems(lambda: shadow)

        item1 = MockQueryItem("/foo")
        item2 = MockQueryItem("/foo")
        obj.update(set([item1, item2]))
        self.assertEquals(set([item1, item2]), obj)
        self.assertEquals(set([item1.vpath, item2.vpath]), shadow)

        item3 = MockQueryItem("/foo")
        shadow2 = set()
        obj2 = TaskQueryItems(lambda: shadow2, set([item3]))
        obj.update(obj2)
        self.assertEquals(set([item1, item2, item3]), obj)
        self.assertEquals(set([item1.vpath, item2.vpath, item3.vpath]), shadow)

    def test_clear(self):
        shadow = set()
        obj = TaskQueryItems(lambda: shadow)

        item1 = MockQueryItem("/foo")
        item2 = MockQueryItem("/foo")
        obj.update(set([item1, item2]))
        obj.clear()
        self.assertEquals(set([]), obj)
        self.assertEquals(set([]), shadow)

    def test_deserialize(self):
        class MockModelManager(object):
            def get_item(self, vpath):
                if vpath == "/foo":
                    return MockQueryItem(vpath)
                return None

        items = set(["/foo", "/bar"])
        obj = TaskQueryItems.deserialize(lambda: items, MockModelManager())
        self.assertEquals(
            set(["/foo"]),
            set([item.vpath for item in obj])
        )

        item = MockQueryItem("/foobar")
        obj.add(item)
        self.assertEquals(
            set(["/foo", "/foobar"]),
            set([item.vpath for item in obj])
        )
