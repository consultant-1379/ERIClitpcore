from litp.migration import BaseMigration
from litp.migration.operations import AddCollection


class Migration(BaseMigration):
    version = '1.14.4'
    operations = [AddCollection('software', 'images', 'image-base')]
