from litp.migration import BaseMigration
from litp.migration.operations import AddProperty


class Migration(BaseMigration):
    version = '1.18.2'
    operations = [
        AddProperty('ha-service-config', 'service_id', None),
        AddProperty('ha-service-config', 'dependency_list', None)
    ]
