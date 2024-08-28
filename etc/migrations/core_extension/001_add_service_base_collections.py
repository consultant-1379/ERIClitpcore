from litp.migration import BaseMigration
from litp.migration.operations import AddCollection, AddRefCollection


class Migration(BaseMigration):
    version = '1.8.19'
    operations = [AddCollection('software', 'services', 'service-base'),
                  AddRefCollection('node', 'services', 'service-base'), ]
