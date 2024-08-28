from litp.core.plugin import Plugin
from litp.core.task import CallbackTask, ConfigTask
from litp.core.exceptions import CallbackExecutionException


class Dummy10449Plugin(Plugin):

    def __init__(self):
        self.rpc_callbacks = {'future_uuid': self._cb}

    def create_configuration(self, api):
        ms = api.query_by_vpath('/ms')

        # Purge task
        purge_disk = api.query_by_vpath('/ms/system/disks/disk0')
        purge_desc = 'Purge existing partitions and volume groups ' \
               'from disk "{0}" on node "{1}"'.format(purge_disk.name,
                                                      ms.hostname)
        purge_task = CallbackTask(purge_disk, purge_desc,
                self.rpc_callbacks['future_uuid'], [ms.hostname],
                'killpart', 'clear', uuidfromview=purge_disk.get_vpath())

        # Network-interface task
        interface = api.query_by_vpath('/ms/network_interfaces/ip1')
        net_task = ConfigTask(ms,
                interface,
                'Configure %s "%s" on node "%s"' %
                (interface.item_type_id, interface.network_name,
                    ms.hostname),
            'network::config',
            interface.network_name,
            ensure='present', bootproto='static',
            onboot='yes', nozeroconf='yes',
            userctl='no')

        # Firewall task
        action = 'Add'
        rule = api.query_by_vpath('/ms/configs/fw_config/rules/fw_basetcp')
        fire_desc = '%s firewall rule "%s" on node "%s"' % (
            action, rule.name, ms.hostname)
        rule_id = '0'
        properties = {'test': 'test'}
        fire_task = ConfigTask(node=ms,
            model_item=rule,
            description=fire_desc,
            call_type="firewalls::rules",
            call_id=rule_id,
            **properties
        )

        return [purge_task, net_task, fire_task]

    def _cb(self, api):
        pass
