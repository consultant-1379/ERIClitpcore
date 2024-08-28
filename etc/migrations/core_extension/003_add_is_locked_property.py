from litp.migration import BaseMigration
from litp.migration.operations import AddProperty


class Migration(BaseMigration):
    version = '1.8.26'
    operations = [AddProperty('node', 'is_locked', 'false')]
