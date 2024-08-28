from litp.core.extension import ModelExtension
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Collection
from litp.core.plugin import Plugin
from litp.core.execution_manager import CallbackTask


class Dummy200916Extension(ModelExtension):

    def define_item_types(self):

        return [
            ItemType("dummy-filesystem",
                item_description="This item type represents"
                                 " the file system"
                                 " that will be created on the SFS.",
                extend_item="file-system-base",
                path=Property('any_string',
                    prop_description="The path of the SFS file system "
                                     "that will be created on the SFS.",
                    required=True),
                size=Property("any_string",
                    prop_description="The size of the file system"
                                     " to be created.",
                    required=True,
                    configuration=True),
                backup_policy=Property('any_string',
                    prop_description="Used to specify how the file "
                           "system should be backed up (from snapshot or "
                           "direct).",
                    required=False,
                    configuration=False),
                snap_size=Property('any_string',
                    prop_description="The percentage of the file system size "
                                    "that is used to calculate the size of "
                                    "the sfs shared cache object.",
                    required=False,
                    configuration=False),
                config_prop=Property("any_string",
                    prop_description="A dummy configuration property that"
                                    "is not required and has no default.",
                    required=False),
                non_config_prop=Property("any_string",
                    prop_description="A dummy non configuration property that"
                                    "is not required and has no default.",
                    required=False,
                    configuration=False),
                req_non_config_prop=Property('any_string',
                    prop_description="A dummy property, used to test a non- "
                                    "config property that is required.",
                    required=True,
                    configuration=False),
                non_config_default=Property('any_string',
                    prop_description="A dummy property, used to test a non- "
                                    "config property that has a default value.",
                    required=False,
                    configuration=False,
                    default='non-config'),

            ),
            ItemType('storage-profile',
                item_description='A storage-profile.',
                extend_item='storage-profile-base',
                file_systems=Collection('dummy-filesystem',
                                         min_count=1, max_count=255),
            ),
        ]

class Dummy200916Plugin(Plugin):

    def create_configuration(self, api):
        """
        To be used only with test_25_non_config_plugin.
        dummy_config_task should always be generated
        dummy_non_config_task should never be generated
        """
        tasks = []
        file_systems = api.query('dummy-filesystem')
        conf = "config_prop"
        non_conf = "non_config_prop"
        for fs in file_systems:
            # Check if non_config_prop exists, if it doesn't, it's been deleted
            # or the item has been created and no non-config tasks should be generated
            if non_conf in fs.applied_properties.keys() and \
                conf in fs.applied_properties.keys():
                # Check if non_config_prop and config_prop is in applied_properties
                # and state is updated. If all conditions are met, this indicates
                # a configuration change. This non-config task should never be generated.
                if (fs.applied_properties[conf] == fs.config_prop and \
                    fs.applied_properties[non_conf] == fs.non_config_prop) \
                        and fs.get_state() == 'Updated':
                    tasks.append(CallbackTask(fs, 'dummy_non_config_task', \
                                              self.non_config_task))
            # Check if config_prop exists, if it doesn't, it's either been
            # deleted or the item has just been created
            if conf in fs.applied_properties.keys():
                # Check if config_prop is not in applied properties. If it has a
                # configuration change has been made and a task needs to be generated
                if fs.applied_properties[conf] != fs.config_prop and \
                        fs.get_state() == 'Updated':
                    tasks.append(CallbackTask(fs, 'dummy_config_task', \
                                          self.config_task))
            # If config_props is not in applied_properties and is in Initial, it
            # has just been created and a config_task needs to be generated
            elif fs.get_state() == 'Initial':
                tasks.append(CallbackTask(fs, 'dummy_config_task', \
                                      self.config_task))

        return tasks

    def non_config_task(self, api):
        pass

    def config_task(self, api):
        pass
