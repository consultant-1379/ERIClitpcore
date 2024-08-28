from litp.migration import BaseMigration
from litp.migration.operations import AddCollection, AddRefCollection


class Migration(BaseMigration):
    version = '1.10.5'
    operations = [AddRefCollection('clustered-service', 'applications', 'service'),]
