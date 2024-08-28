from litp.migration import BaseMigration
from litp.migration.operations import AddCollection, AddRefCollection


class Migration(BaseMigration):
    version = '1.8.22'
    operations = [AddCollection('root', 'litp', 'litp-service-base'),]
