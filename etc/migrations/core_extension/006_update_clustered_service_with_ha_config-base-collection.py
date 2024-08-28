from litp.migration import BaseMigration
from litp.migration.operations import AddCollection, AddRefCollection


class Migration(BaseMigration):
    version = '1.11.1'
    operations = [AddCollection('clustered-service', 'ha_configs', 'ha-config-base'),]
