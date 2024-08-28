import unittest

from litp.core.model_manager import QueryItem
from litp.core.task_dependencies import TaskDependencies


class MockQueryItem(object):
    def __init__(self, vpath):
        self.vpath = vpath


MockQueryItem.__name__ = "QueryItem"


class MockTask(object):
    def __init__(self, unique_id):
        self.unique_id = unique_id


class TestTaskDependencies(unittest.TestCase):
    def test_init(self):
        shadow = set()
        item = MockQueryItem("/foo")
        task = MockTask("unique_id")
        ctci = ("ct", "ci")

        obj = TaskDependencies(lambda: shadow, set([item, task, ctci]))
        self.assertEquals(set([item, task, ctci]), obj)
        self.assertEquals(set([
            ("q", item.vpath),
            ("t", task.unique_id),
            ("c", ctci[0], ctci[1])
        ]), shadow)

    def test_add(self):
        shadow = set()
        obj = TaskDependencies(lambda: shadow)

        item = MockQueryItem("/foo")
        task = MockTask("unique_id")
        ctci = ("ct", "ci")

        obj.add(item)
        self.assertEquals(set([item]), obj)
        self.assertEquals(set([
            ("q", item.vpath)
        ]), shadow)

        obj.add(task)
        self.assertEquals(set([item, task]), obj)
        self.assertEquals(set([
            ("q", item.vpath),
            ("t", task.unique_id)
        ]), shadow)

        obj.add(ctci)
        self.assertEquals(set([item, task, ctci]), obj)
        self.assertEquals(set([
            ("q", item.vpath),
            ("t", task.unique_id),
            ("c", ctci[0], ctci[1])
        ]), shadow)

    def test_remove(self):
        shadow = set()
        obj = TaskDependencies(lambda: shadow)

        item = MockQueryItem("/foo")
        item = MockQueryItem("/foo")
        task = MockTask("unique_id")
        ctci = ("ct", "ci")
        obj.add(item)
        obj.add(task)
        obj.add(ctci)

        obj.remove(item)
        self.assertEquals(set([task, ctci]), obj)
        self.assertEquals(set([
            ("t", task.unique_id),
            ("c", ctci[0], ctci[1])
        ]), shadow)

        obj.remove(task)
        self.assertEquals(set([ctci]), obj)
        self.assertEquals(set([
            ("c", ctci[0], ctci[1])
        ]), shadow)

        obj.remove(ctci)
        self.assertEquals(set([]), obj)
        self.assertEquals(set([]), shadow)

    def test_update(self):
        shadow = set()
        obj = TaskDependencies(lambda: shadow)

        item = MockQueryItem("/foo")
        task = MockTask("unique_id")

        obj.update(set([item, task]))
        self.assertEquals(set([item, task]), obj)
        self.assertEquals(set([
            ("q", item.vpath),
            ("t", task.unique_id)
        ]), shadow)

        ctci = ("ct", "ci")
        shadow2 = set()
        obj2 = TaskDependencies(lambda: shadow2, set([ctci]))
        obj.update(obj2)
        self.assertEquals(set([item, task, ctci]), obj)
        self.assertEquals(set([
            ("q", item.vpath),
            ("t", task.unique_id),
            ("c", ctci[0], ctci[1])
        ]), shadow)

    def test_clear(self):
        shadow = set()
        obj = TaskDependencies(lambda: shadow)

        item = MockQueryItem("/foo")
        task = MockTask("unique_id")
        ctci = ("ct", "ci")

        obj.update(set([item, task, ctci]))
        obj.clear()
        self.assertEquals(set([]), obj)
        self.assertEquals(set([]), shadow)

    def test_deserialize(self):
        class MockModelManager(object):
            def get_item(self, vpath):
                if vpath == "/foo":
                    return MockQueryItem(vpath)
                return None

        class MockDataManager(object):
            def get_task_by_unique_id(self, unique_id):
                if unique_id == "unique_id":
                    return MockTask(unique_id)
                return None

        items = set([
            ("q", "/foo"),
            ("q", "/bar"),
            ("t", "unique_id"),
            ("t", "other_unique_id"),
            ("c", "foo", "bar")
        ])
        obj = TaskDependencies.deserialize(lambda: items, MockDataManager(), MockModelManager())
        self.assertEquals(
            set(["/foo"]),
            set([item.vpath for item in obj if isinstance(item, QueryItem)])
        )
        self.assertEquals(
            set(["unique_id"]),
            set([item.unique_id for item in obj if isinstance(item, MockTask)])
        )
        self.assertEquals(
            set([("foo", "bar")]),
            set([item for item in obj if isinstance(item, tuple)])
        )
