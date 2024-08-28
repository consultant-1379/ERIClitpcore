from litp.migration.utils import normalize_version


class BaseMigration(object):
    """
    Base class for a model migration.

    **Example Usage:**

    .. code-block:: python

        class Migration(BaseMigration):
            version = '1.0.22'
            operations = [
                AddProperty('package', 'new_prop1', 'value1'),
            ]
    """

    operations = []
    version = None

    def __cmp__(self, other):
        return cmp(self.normalized_version, other.normalized_version)

    def __repr__(self):
        return "<%s - %s>" % (self.__module__, self.version)

    @property
    def normalized_version(self):
        return normalize_version(self.version)[:-1]

    def forwards(self, model_manager):
        for operation in self.operations:
            operation.mutate_forward(model_manager)

    def backwards(self, model_manager):
        for operation in self.operations:
            operation.mutate_backward(model_manager)
