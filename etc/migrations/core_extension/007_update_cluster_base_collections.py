from litp.migration import BaseMigration
from litp.migration.operations import UpdateCollectionType


class Migration(BaseMigration):
    version = '1.11.12'
    operations = [UpdateCollectionType('deployment', 'clusters', 'cluster',
                                       'cluster-base')]
