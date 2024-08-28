class BackupException(Exception):
    errno = 1


class TemplateBackupException(BackupException):
    def __init__(self, *args):
        message = self._template.format(*args)
        super(TemplateBackupException, self).__init__(message)


class MessageBackupException(BackupException):
    def __init__(self):
        message = self._message
        super(MessageBackupException, self).__init__(message)


class MissingDirectoryException(TemplateBackupException):
    _template = "Specified path '{0}' is not a directory."


class PermissionException(MessageBackupException):
    _message = 'Permission denied.'


class TarException(TemplateBackupException):
    _template = "tar command exited with {0}"


class NotRequiredException(MessageBackupException):
    errno = 0
    _message = "No backup required."


class MissingManifestException(TemplateBackupException):
    errno = 2
    _template = "ERROR: File \"{0}\" does not exist!"


class PgRestoreException(TemplateBackupException):
    _template = ("pgrestore failed with returncode {0}.\n"
                  "STDOUT:\n===\n{1}\n"
                  "STDERR:\n===\n{2}\n")


class PgDumpException(TemplateBackupException):
    _template = ("pgdump failed with returncode {0}.\n"
               "STDOUT:\n===\n{1}\n"
               "STDERR:\n===\n{2}\n")


class BinaryException(TemplateBackupException):
    _template = "Failed to execute binary {0}."


class OldFashionedBackupException(TemplateBackupException):
    _template = ("Backup {0} is outdated. "
                 "It contains LAST_KNOWN_CONFIG, not PostgreSQL binary dump")


class BackupIncompleteManifestsMissingException(TemplateBackupException):
    _template = ("Backup {0} is incomplete. "
                 "Mandatory manifest(s) are missing: {1}.")


class BackupIncompleteDumpMissingException(TemplateBackupException):
    _template = ("Backup {0} is incomplete. "
                 "Binary dump is missing.")
