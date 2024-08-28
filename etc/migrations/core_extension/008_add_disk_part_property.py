from litp.migration import BaseMigration
from litp.migration.operations import AddProperty


class Migration(BaseMigration):
    version = '1.13.36'
    operations = [AddProperty('disk', 'disk_part', 'false')]
