from litp.migration import BaseMigration
from litp.migration.operations import AddProperty


class Migration(BaseMigration):
    version = '1.22.5'
    operations = [
        AddProperty('ha-service-config', 'fault_on_monitor_timeouts', '4'),
        AddProperty('ha-service-config', 'tolerance_limit', '0'),
        AddProperty('ha-service-config', 'clean_timeout', '60')
    ]
