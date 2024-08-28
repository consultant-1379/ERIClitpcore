from litp.migration import BaseMigration
from litp.migration.operations import AddProperty


class Migration(BaseMigration):
    version = '1.2.4'
    operations = [AddProperty('package', 'prop1', 'abc'),
                  RemoveProperty('package', 'prop2', 'def'),
                  AddProperty('package', 'prop3', 'ghi'),
    ]
