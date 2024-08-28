from litp.migration import BaseMigration
from litp.migration.operations import AddProperty


class Migration(BaseMigration):
    version = '1.53.1'
    operations = [AddProperty('deployment', 'in_restore_mode', 'false')]
