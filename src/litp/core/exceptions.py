

class ModelManagerException(Exception):
    pass


class CorruptedConfFileException(Exception):
    pass


class CyclicGraphException(Exception):
    def __init__(self, message, graph=None):
        super(CyclicGraphException, self).__init__(message)
        self.graph = graph


class BadRebootException(Exception):
    pass


class ConfigValueError(ValueError):
    pass


class DuplicateChildTypeException(Exception):
    pass


class DuplicatedItemTypeException(Exception):
    pass


class DuplicatedPropertyTypeException(Exception):
    pass


class EmptyPlanException(Exception):
    pass


class InvalidIsoException(Exception):
    pass


class ModelItemContainerException(Exception):
    pass


class DataIntegrityException(Exception):
    pass


class NoCredentialsException(Exception):
    pass


class NodeLockException(Exception):
    pass


class NoMatchingActionError(Exception):
    pass


class NonUniqueTaskException(Exception):
    pass


class NotModelItemException(Exception):
    pass


class PlanStateError(Exception):
    def __init__(self, msg, state=''):
        super(PlanStateError, self).__init__(msg)
        self.state = state


class RegistryException(Exception):
    pass


class SchemaWriterException(Exception):
    """
    Base Exception raised by SchemaWriter
    """
    pass


class ServiceKilledException(Exception):
    pass


class SnapshotError(Exception):
    pass


class TaskValidationException(Exception):
    def __init__(self, message, messages=None):
        super(TaskValidationException, self).__init__(message)
        if messages is None:
            self.messages = []
        self.messages = messages


class CallbackExecutionException(Exception):
    """ callback exception"""
    pass


class NoSnapshotItemError(Exception):
    pass


class PlanStoppedException(Exception):
    pass


class RemoteExecutionException(Exception):
    pass


class RpcExecutionException(Exception):
    pass


class McoRunError(Exception):
    pass


class McoTimeoutException(Exception):
    def __init__(self, message, result=None):
        super(McoTimeoutException, self).__init__(self, message)
        if result is None:
            result = {}
        self.result = result


class McoFailed(Exception):
    def __init__(self, message, result=None):
        super(McoFailed, self).__init__(message)
        if result is None:
            result = {}
        self.result = result


class IncorrectMergeTypesException(Exception):
    pass


class XMLExportException(Exception):
    pass


class LinksNotSupportedException(XMLExportException):
    pass


class MissingIdentifierException(Exception):
    pass


class ViewError(Exception):
    pass


class PluginError(Exception):
    pass


class ForkError(Exception):
    pass


class FieldSorterException(Exception):
    pass


class FailedTasklessPuppetEvent(Exception):
    pass
