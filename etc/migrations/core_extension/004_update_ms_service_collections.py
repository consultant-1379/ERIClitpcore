from litp.migration import BaseMigration
from litp.migration.operations import UpdateCollectionType


class Migration(BaseMigration):
    version = '1.10.9'
    operations = [UpdateCollectionType('ms', 'services', 'ms-service', 'service-base')]
