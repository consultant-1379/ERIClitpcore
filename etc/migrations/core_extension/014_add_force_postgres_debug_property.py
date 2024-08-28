from litp.migration import BaseMigration
from litp.migration.operations import AddProperty


class Migration(BaseMigration):
    version = '1.80.6'
    operations = [AddProperty('logging', 'force_postgres_debug', 'false')]
