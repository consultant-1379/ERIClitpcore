from litp.migration import BaseMigration
from litp.migration.operations import AddCollection, AddRefCollection


class Migration(BaseMigration):
    version = '1.78.6'
    operations = [AddCollection('storage', 'managed_files',
                                'managed-file-base'),
                  AddRefCollection('node', 'managed_files',
                                   'managed-file-base'),
                  AddRefCollection('cluster', 'managed_files',
                                   'managed-file-base'),
                  AddRefCollection('ms', 'managed_files',
                                   'managed-file-base'),
                  ]