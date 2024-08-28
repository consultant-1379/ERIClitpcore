from litp.core.plugin import Plugin
from litp.core.task import ConfigTask


class Dummy12781Plugin(Plugin):

    def sorted_items(self, to_query, item_type_id):
        items = to_query.query(item_type_id)
        items.sort(key=lambda qi: qi.vpath)
        return items

    def create_configuration(self, api):
        tasks = []
        for node in api.query("node"):
            # TC01: 3 items -> return 2 persisted (one explicitly, one by default) and one non persisted
            for index, test_item in enumerate(
                    self.sorted_items(node, "test_12781_tc01")):
                task = ConfigTask(node, test_item, "", test_item.item_id,
                        test_item.item_type.item_type_id)
                if index == 0:
                    task.persist = False
                elif index == 1:
                    task.persist = True
                task.description = "Persist: {0}".format(task.persist)
                tasks.append(task)
            # TC02: Return one task, but switch persist flag for next plan
            for index, test_item in enumerate(
                    self.sorted_items(node, "test_12781_tc02")):
                task = ConfigTask(node, test_item, "", test_item.item_id,
                        test_item.item_type.item_type_id)
                if test_item.is_updated() and test_item.name == "up":
                    task.persist = False
                elif test_item.is_applied() and test_item.name == "up":
                    task.persist = False
                elif test_item.is_updated() and test_item.name == "up_two":
                    task.persist = True
                task.description = "Persist: {0}".format(task.persist)
                tasks.append(task)
            # TC03: Two non persisted tasks, one dependent on the other
            for index, test_item in enumerate(
                    self.sorted_items(node, "test_12781_tc03")):
                task = ConfigTask(node, test_item, "", test_item.item_id,
                        test_item.item_type.item_type_id)
                task.persist = False
                task.description = "Persist: {0}".format(task.persist)
                if tasks:
                    task.requires.add(tasks[index - 1])
                tasks.append(task)
            # TC04 & TC05: A persisted task depends on a non persisted task
            for index, test_item in enumerate(
                    self.sorted_items(node, "test_12781_tc04")):
                task = ConfigTask(node, test_item, "", test_item.item_id,
                        test_item.item_type.item_type_id)
                if index == 0:
                    task.persist = False
                task.description = "Persist: {0}".format(task.persist)
                if tasks:
                    task.requires.add(tasks[index - 1])
                tasks.append(task)
            # TC06: A non persisted task depends on a persisted task
            for index, test_item in enumerate(
                    self.sorted_items(node, "test_12781_tc06")):
                task = ConfigTask(node, test_item, "", test_item.item_id,
                        test_item.item_type.item_type_id)
                if index == 1:
                    task.persist = False
                    task.requires.add(tasks[index - 1])
                task.description = "Persist: {0}".format(task.persist)
                tasks.append(task)
            # TC07: A non persisted task depends on ForRemoval persisted task
            if node.query("test_12781_tc07"):
                test_item = api.query_by_vpath("/deployments/local/clusters/"
                    "cluster1/nodes/node1/services/one")
                test_item2 = api.query_by_vpath("/deployments/local/clusters/"
                    "cluster1/nodes/node1/services/two")
                if test_item and test_item.is_initial():
                    task = ConfigTask(node, test_item, "", test_item.item_id,
                            test_item.item_type.item_type_id)
                    task.description = "Persist: {0}".format(task.persist)
                    return [task]
                elif test_item2 and test_item.is_for_removal():
                    task2 = ConfigTask(node, test_item2, "", test_item2.item_id,
                            test_item2.item_type.item_type_id)
                    task2.persist = False
                    task2.description = "Persist: {0}".format(task2.persist)
                    task2.requires.add(test_item)
                    # Generate replacement task for 'test_item' using 'replaces'
                    replace_task = ConfigTask(node, test_item,
                            "Plugin replacement task",
                            "replace_type", "replace_id")
                    replace_task.replaces.add((test_item.item_id,
                            test_item.item_type.item_type_id))
                    return [task2, replace_task]
            # TC08: A non persisted task depends on ForRemoval persisted task
            if node.query("test_12781_tc08"):
                test_item = api.query_by_vpath("/deployments/local/clusters/"
                    "cluster1/nodes/node1/services/one")
                test_item2 = api.query_by_vpath("/deployments/local/clusters/"
                    "cluster1/nodes/node1/services/two")
                if test_item and test_item.is_initial():
                    task = ConfigTask(node, test_item, "", test_item.item_id,
                            test_item.item_type.item_type_id)
                    task.description = "Persist: {0}".format(task.persist)
                    return [task]
                elif test_item2 and test_item.is_for_removal():
                    task2 = ConfigTask(node, test_item2, "", test_item2.item_id,
                            test_item2.item_type.item_type_id)
                    task2.persist = False
                    task2.description = "Persist: {0}".format(task2.persist)
                    task2.requires.add(test_item)
                    # Generate a replacement task for 'test_item' using the
                    # same call type call id as test items original task
                    replace_task = ConfigTask(node, test_item2,
                            "Plugin replacement task", test_item.item_id,
                            test_item.item_type.item_type_id)
                    return [task2, replace_task]

            # TC09: exlpicitly replace persisted task with not persisted, one dummy task
            for index, test_item in enumerate(
                    self.sorted_items(node, "test_12781_tc09")):
                if test_item.name == "unrelated_item":
                    task = ConfigTask(node, test_item, "", test_item.item_id,
                            test_item.item_type.item_type_id)
                    task.description = "dummy task"
                    tasks.append(task)

                if test_item.is_updated() and test_item.name == "updated":
                    task = ConfigTask(node, test_item, "", test_item.item_id,
                            test_item.item_type.item_type_id)
                    task.persist = False
                    task.description = "replacement task - " \
                            "Persist: {0}".format(task.persist)
                    task.replaces.add((
                        test_item.item_id, test_item.item_type.item_type_id
                    ))
                    tasks.append(task)
                elif test_item.is_initial() and test_item.name == "initial":
                    task = ConfigTask(node, test_item, "", test_item.item_id,
                            test_item.item_type.item_type_id)
                    task.description = "Persist: {0}".format(task.persist)
                    tasks.append(task)

            # TC10: override persisted task with not persisted, one dummy task
            for index, test_item in enumerate(
                    self.sorted_items(node, "test_12781_tc10")):
                if test_item.name == "unrelated_item":
                    task = ConfigTask(node, test_item, "", test_item.item_id,
                            test_item.item_type.item_type_id)
                    task.description = "dummy task"
                    tasks.append(task)

                if test_item.is_updated() and test_item.name == "updated":
                    task = ConfigTask(node, test_item, "", test_item.item_id,
                            test_item.item_type.item_type_id)
                    task.persist = False
                    task.description = "replacement task - " \
                            "Persist: {0}".format(task.persist)
                    tasks.append(task)
                elif test_item.is_initial() and test_item.name == "initial":
                    task = ConfigTask(node, test_item, "", test_item.item_id,
                            test_item.item_type.item_type_id)
                    task.description = "Persist: {0}".format(task.persist)
                    tasks.append(task)

            # TC11: failed non persisted task, one dummy task
            for index, test_item in enumerate(
                    self.sorted_items(node, "test_12781_tc11")):
                if test_item.name == "unrelated_item":
                    task = ConfigTask(node, test_item, "", test_item.item_id,
                            test_item.item_type.item_type_id)
                    task.description = "dummy task"
                    tasks.append(task)
                if test_item.name == "testme":
                    task = ConfigTask(node, test_item, "", "failme",
                            test_item.item_type.item_type_id)
                    task.persist = False
                    task.description = "Persist: {0}".format(task.persist)
                    tasks.append(task)

        return tasks
