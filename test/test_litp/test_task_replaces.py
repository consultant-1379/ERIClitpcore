import unittest

from litp.core.task_replaces import TaskReplaces


class TestTaskReplaces(unittest.TestCase):
    def test_init(self):
        shadow = set()
        ctci = ("ct", "ci")

        obj = TaskReplaces(lambda: shadow, set([ctci]))
        self.assertEquals(set([ctci]), obj)
        self.assertEquals(set([
            ("c", ctci[0], ctci[1])
        ]), shadow)

    def test_add(self):
        shadow = set()
        obj = TaskReplaces(lambda: shadow)

        ctci = ("ct", "ci")
        obj.add(ctci)
        self.assertEquals(set([ctci]), obj)
        self.assertEquals(set([
            ("c", ctci[0], ctci[1])
        ]), shadow)

    def test_remove(self):
        shadow = set()
        obj = TaskReplaces(lambda: shadow)

        ctci = ("ct", "ci")
        obj.add(ctci)
        obj.remove(ctci)
        self.assertEquals(set([]), obj)
        self.assertEquals(set([]), shadow)

    def test_update(self):
        shadow = set()
        obj = TaskReplaces(lambda: shadow)

        ctci1 = ("ct1", "ci1")
        ctci2 = ("ct2", "ci2")
        obj.update(set([ctci1, ctci2]))
        self.assertEquals(set([ctci1, ctci2]), obj)
        self.assertEquals(set([
            ("c", ctci1[0], ctci1[1]),
            ("c", ctci2[0], ctci2[1])
        ]), shadow)

        ctci3 = ("ct3", "ci3")
        shadow2 = set()
        obj2 = TaskReplaces(lambda: shadow2, set([ctci3]))
        obj.update(obj2)
        self.assertEquals(set([ctci1, ctci2, ctci3]), obj)
        self.assertEquals(set([
            ("c", ctci1[0], ctci1[1]),
            ("c", ctci2[0], ctci2[1]),
            ("c", ctci3[0], ctci3[1])
        ]), shadow)

    def test_clear(self):
        shadow = set()
        obj = TaskReplaces(lambda: shadow)

        ctci1 = ("ct1", "ci1")
        ctci2 = ("ct2", "ci2")
        obj.update(set([ctci1, ctci2]))
        obj.clear()
        self.assertEquals(set([]), obj)
        self.assertEquals(set([]), shadow)

    def test_deserialize(self):
        items = set([("c", "foo1", "bar1"), ("c", "foo2", "bar2")])
        obj = TaskReplaces.deserialize(lambda: items)
        self.assertEquals(
            set([("foo1", "bar1"), ("foo2", "bar2")]),
            set([item for item in obj if isinstance(item, tuple)])
        )

        ctci = ("ct", "ci")
        obj.add(ctci)
        self.assertEquals(
            set([("foo1", "bar1"), ("foo2", "bar2"), ("ct", "ci")]),
            set([item for item in obj if isinstance(item, tuple)])
        )
