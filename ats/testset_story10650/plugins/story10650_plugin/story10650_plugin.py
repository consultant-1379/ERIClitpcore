from litp.core.plugin import Plugin
from litp.core.task import ConfigTask


class Story10650Plugin(Plugin):
    """Test plugin for LITPCDS-10650"""

    def create_configuration(self, api):
        tasks = []
        task = None
        task1 = None
        task2 = None
        task3 = None
        taskA = None

        for node in api.query("node"):

            # TC01/TC02
            for item in node.query("story10650"):
                if item.name=="tc01_foobar1" and item.is_initial():
                    task1 = ConfigTask(
                        node, item, "", "foo1", "bar1", name=item.name)
                    task2 = ConfigTask(
                        node, item, "", "foo2", "bar2", name=item.name)
                    task3 = ConfigTask(
                        node, item, "", "foo3", "bar3", name=item.name)
                    tasks.append(task1)
                    tasks.append(task2)
                    task3.requires.add(task2)
                    tasks.append(task3) 

            for item in node.query("story10650"):
                if item.name=="tc01_foobar2" and item.is_updated():
                    task4 = ConfigTask(
                        node, item, "", "foo4", "bar4", name=item.name)
                    task5 = ConfigTask(
                        node, item, "", "foo5", "bar5", name=item.name)
                    task4.replaces.add(("foo1", "bar1"))
                    task5.replaces.add(("foo2", "bar2"))
                    task5.replaces.add(("foo3", "bar3"))
                    tasks.append(task4)
                    tasks.append(task5)

            for item in node.query("story10650"):
                if item.name=="tc01_foobar3" and item.is_updated():
                    task4 = ConfigTask(
                        node, item, "", "foo4", "bar4", name=item.name)
                    task5 = ConfigTask(
                        node, item, "", "foo5", "bar5", name=item.name)
                    task4.replaces.add(("foo1", "bar1"))
                    task5.replaces.add(("foo2", "bar2"))
                    task5.replaces.add(("foo3", "bar3"))
                    tasks.append(task4)
                    tasks.append(task5) 

            # TC03
            for item in node.query("story10650"):
                if item.name=="tc03_foobar1" and item.is_initial():
                    task1 = ConfigTask(
                        node, item, "", "foo1", "bar1", name=item.name)
                    task2 = ConfigTask(
                        node, item, "", "foo2", "bar2", name=item.name)
                    task3 = ConfigTask(
                        node, item, "", "foo3", "bar3", name=item.name)

                    tasks.append(task1)
                    tasks.append(task2)
                    task3.requires.add(task2)
                    tasks.append(task3)

            for item in node.query("story10650"):
                if item.name=="tc03_foobar2" and item.is_updated():
                    task4 = ConfigTask(
                        node, item, "", "foo4", "bar4", name=item.name)
                    task5 = ConfigTask(
                        node, item, "", "foo5", "bar5", name=item.name)
                    task4.replaces.add(("foo1", "bar1"))
                    task5.replaces.add(("foo2", "bar2"))
                    task5.replaces.add(("foo6", "bar6"))
                    tasks.append(task4)
                    tasks.append(task5)

            # TC04
            for item in node.query(
                    "story10650", name="tc04_foobar1"):
                task1 = ConfigTask(
                    node, item, "", "foo1", "bar1", name=item.name)
                tasks.append(task1)

            for item in node.query(
                    "story10650", name="tc04_foobar2"):
                task2 = ConfigTask(
                    node, item, "", "foo2", "bar2", name=item.name)
                task3 = ConfigTask(
                    node, item, "", "foo3", "bar3", name=item.name)
                task3.replaces.add(("foo2", "bar2"))
                task3.replaces.add(("foo1", "bar1"))
                tasks.append(task2)
                tasks.append(task3) 

            # TC05
            for item in node.query(
                    "story10650", name="tc05_foobar1"):
                task1 = ConfigTask(
                    node, item, "", "foo1", "bar1", name=item.name)
                task2 = ConfigTask(
                    node, item, "", "foo2", "bar2", name=item.name)
                tasks.append(task1)
                tasks.append(task2)

            for item in node.query(
                    "story10650", name="tc05_foobar2"):
                task3 = ConfigTask(
                    node, item, "", "foo3", "bar3", name=item.name)
                task4 = ConfigTask(
                    node, item, "", "foo4", "bar4", name=item.name)
                task3.replaces.add(("foo1", "bar1"))
                task4.replaces.add(("foo1", "bar1"))
                tasks.append(task3)
                tasks.append(task4)

            # TC06
            for item in node.query(
                    "story10650", name="tc06_foobar1"):
                task6 = ConfigTask(
                    node, item, "", "foo6", "bar6", name=item.name)
                task6.replaces.add(("foo6", "bar6"))
                tasks.append(task6)

            # TC11 
            for item in node.query("story10650"):
                if item.name=="tc11_foobar1":
                    task1 = ConfigTask(
                        node, item, "", "foo1", "bar1", name=item.name)
                    tasks.append(task1)

            for item in node.query("story10650"):
                if item.name=="tc11_foobar2":
                    taskA = ConfigTask(
                        node, item, "", "fooX", "barY", name=item.name)
                    taskA.replaces.add(("foo1", "bar1"))
                    tasks.append(taskA)

            # TC07/TC12
            for item in node.query("story10650"):
                if item.name=="tc07_foobar1" or item.name=="tc12_foobar1":
                    task1 = ConfigTask(
                        node, item, "", "foo1", "bar1", name=item.name)
                    task2 = ConfigTask(
                        node, item, "", "foo2", "bar2", name=item.name)
                    task3 = ConfigTask(
                        node, item, "", "foo3", "bar3", name=item.name)

                    task1.requires.add(task2)
                    task1.requires.add(task3)
                    tasks.append(task1)
                    tasks.append(task2)
                    tasks.append(task3)

            for item in node.query("story10650"):
                if item.name=="tc07_foobar2" or item.name=="tc12_foobar2":
                    task4 = ConfigTask(
                        node, item, "", "foo4", "bar4", name=item.name)
                    task4.replaces.add(("foo1", "bar1"))
                    tasks.append(task4)

            # TC08/TC13
            for item in node.query("story10650"):
                if item.name=="tc08_foobar1" or item.name=="tc09_foobar1":
                    task1 = ConfigTask(
                        node, item, "", "foo1", "bar1", name=item.name)
                    task2 = ConfigTask(
                        node, item, "", "foo2", "bar2", name=item.name)
                    task3 = ConfigTask(
                        node, item, "", "foo3", "bar3", name=item.name)

                    task1.requires.add(task2)
                    task1.requires.add(task3)
                    tasks.append(task1)
                    tasks.append(task2)
                    tasks.append(task3)

                if item.name=="tc13_foobar1":
                    task1 = ConfigTask(
                        node, item, "", "foo1", "bar1", name=item.name)
                    task2 = ConfigTask(
                        node, item, "", "foo2", "bar2", name=item.name)
                    task3 = ConfigTask(
                        node, item, "", "foo3", "bar3", name=item.name)
                    task1.requires.add(task2)
                    tasks.append(task1)
                    tasks.append(task2)
                    tasks.append(task3)

            for item in node.query("story10650"):
                if item.name=="tc08_foobar2":
                    task4 = ConfigTask(
                        node, item, "", "foo4", "bar4", name=item.name)
                    task5 = ConfigTask(
                        node, item, "", "foo5", "bar5", name=item.name)
                    task5.replaces.add(("foo1", "bar1"))
                    task5.requires.add(("foo4", "bar4"))
                    tasks.append(task4)
                    tasks.append(task5)

                if item.name=="tc09_foobar2":
                    task4 = ConfigTask(
                        node, item, "", "foo4", "bar4", name=item.name)
                    task5 = ConfigTask(
                        node, item, "", "foo5", "bar5", name=item.name)
                    task5.replaces.add(("foo1", "bar1"))
                    task5.requires.add(task4)
                    task5.requires.add(("foo3", "bar3"))
                    task5.requires.add(("foo2", "bar2"))
                    tasks.append(task4)
                    tasks.append(task5)

                if item.name=="tc13_foobar2":
                    task5 = ConfigTask(
                        node, item, "", "foo5", "bar5", name=item.name)
                    task5.replaces.add(("foo1", "bar1"))
                    task5.requires.add(("foo3", "bar3"))
                    task5.requires.add(("foo2", "bar2"))
                    tasks.append(task5)

            # TC10/TC14
            for item in node.query("story10650"):
                if item.name=="tc10_foobar1":
                    task1 = ConfigTask(
                        node, item, "", "foo1", "bar1", name=item.name)
                    task2 = ConfigTask(
                        node, item, "", "foo2", "bar2", name=item.name)
                    task3 = ConfigTask(
                        node, item, "", "foo3", "bar3", name=item.name)

                    tasks.append(task1)
                    tasks.append(task2)
                    tasks.append(task3)

                if item.name=="tc14_foobar1":
                    task1 = ConfigTask(
                        node, item, "", "foo1", "bar1", name=item.name)
                    task2 = ConfigTask(
                        node, item, "", "foo2", "bar2", name=item.name)
                    task3 = ConfigTask(
                        node, item, "", "foo3", "bar3", name=item.name)

                    tasks.append(task1)
                    tasks.append(task2)
                    tasks.append(task3)

            for item in node.query("story10650"):
                if item.name=="tc10_foobar2" or item.name=="tc14_foobar2":
                    task4 = ConfigTask(
                        node, item, "", "foo4", "bar4", name=item.name)
                    task4.replaces.add(("foo1", "bar1"))
                    task4.requires.add(("foo2", "bar2"))
                    task4.requires.add(("foo3", "bar3"))
                    tasks.append(task4) 

            # TC15
            for item in node.query(
                "story10650", name="tc15_foobar1"):
                task1 = ConfigTask(
                    node, item, "", "foo1", "bar1", name=item.name)
                task2 = ConfigTask(
                    node, item, "", "foo2", "bar2", name=item.name)
                task3 = ConfigTask(
                    node, item, "", "foo3", "bar3", name=item.name)
                task4 = ConfigTask(
                    node, item, "", "foo4", "bar4", name=item.name)

                task4.requires.add(task3)
                tasks.append(task4)
                task3.requires.add(task2)
                tasks.append(task3)
                task2.requires.add(task1)
                tasks.append(task2)
                depend_ = node.query("depend10650")[0]
                task1.requires.add(depend_)
                tasks.append(task1)

            for item in node.query(
                    "story10650", name="tc15_foobar2"):
                task5 = ConfigTask(
                    node, item, "", "foo5", "bar5", name=item.name)
                task6 = ConfigTask(
                    node, item, "", "foo6", "bar6", name=item.name)
                task5.replaces.add(("foo2", "bar2"))
                task6.replaces.add(("foo4", "bar4"))
                task5.requires.add(("foo1", "bar1"))
                tasks.append(task5)
                task6.requires.add(("foo3", "bar3"))
                tasks.append(task6)

            # TC16
            for item in node.query(
                    "story10650", name="tc16_foobar1"):
                task1 = ConfigTask(
                    node, item, "", "foo1", "bar1", name=item.name)
                task2 = ConfigTask(
                    node, item, "", "foo2", "bar2", name=item.name)

                dep = node.query("depend10650")[0]
                task1.requires.add(dep)
                task2.requires.add(dep)
                tasks.append(task1)
                tasks.append(task2)
                
            for item in node.query(
                    "story10650", name="tc16_foobar2"):
                dep = node.query("depend10650")[0]
                task5 = ConfigTask(
                    node, item, "", "foo5", "bar5", name=item.name)
                task6 = ConfigTask(
                    node, item, "", "foo6", "bar6", name=item.name)
                task5.replaces.add(("foo1", "bar1"))
                task6.replaces.add(("foo2", "bar2"))
                task5.requires.add(dep)
                tasks.append(task5)
                tasks.append(task6)

            # TC17
            for item in node.query("story10650"):
                if item.name=="tc17_foobar1":
                    task1 = ConfigTask(
                        node, item, "", "foo1", "bar1", name=item.name)
                    task2 = ConfigTask(
                        node, item, "", "foo2", "bar2", name=item.name)
                    task3 = ConfigTask(
                        node, item, "", "foo3", "bar3", name=item.name)
                    task4 = ConfigTask(
                        node, item, "", "foo4", "bar4", name=item.name)

                    task1.requires.add(("foo2", "bar2"))
                    task3.requires.add(task4)
                    tasks.append(task1)
                    tasks.append(task2)
                    tasks.append(task3)
                    tasks.append(task4)

            for item in node.query("story10650"):
                if item.name=="tc17_foobar2":
                    task5 = ConfigTask(
                        node, item, "", "foo5", "bar5", name=item.name)
                    task5.replaces.add(("foo1", "bar1"))
                    task5.replaces.add(("foo2", "bar2"))
                    tasks.append(task5)

            # TC18
            for item in node.query("story10650"):
                if item.name=="tc18_foobar1":
                    task1 = ConfigTask(
                        node, item, "", "foo1", "bar1", name=item.name)
                    task2 = ConfigTask(
                        node, item, "", "foo2", "bar2", name=item.name)
                    task3 = ConfigTask(
                        node, item, "", "foo3", "bar3", name=item.name)
                    task4 = ConfigTask(
                        node, item, "", "foo4", "bar4", name=item.name)

                    task1.requires.add(("foo2", "bar2"))
                    task3.requires.add(task4)
                    tasks.append(task1)
                    tasks.append(task2)
                    tasks.append(task3)
                    tasks.append(task4)

                    task5 = ConfigTask(
                        node, item, "", "foo5", "bar5", name=item.name)
                    task5.replaces.add(("foo1", "bar1"))
                    task5.replaces.add(("foo3", "bar3"))
                    task5.replaces.add(("foo6", "bar6"))
                    tasks.append(task5)

            # LITPCDS-12264: Multiple replacing tasks for separate items in same plan
            for item in node.query(
                    "story10650", name="litpcds_12264"):
                task = ConfigTask(
                    node, node, "Node task to be replaced", "foo", "bar", name=item.name)
                tasks.append(task)

                rtask = ConfigTask(
                    node, item, "Replacement task", "foo1", "bar1", name=item.name)
                rtask.replaces.add((task.call_type, task.call_id))
                tasks.append(rtask)

            # LITPCDS-12264: Multiple replacing tasks for same items, multiple times
            for item in node.query(
                    "story10650", name="litpcds_12264_multi"):
                task = ConfigTask(
                    node, node, "Node task to be replaced", "foo", "bar", name=item.name)
                tasks.append(task)

                rtask = ConfigTask(
                    node, item, "Replacement task", "foo1", "bar1", name=item.name)
                rtask.replaces.add((task.call_type, task.call_id))
                tasks.append(rtask)

                r2task = ConfigTask(
                    node, item, "Replacement task", "foo2", "bar2", name=item.name)
                r2task.replaces.add((task.call_type, task.call_id))
                tasks.append(r2task)
        return tasks
