from litp.data.constants import (
    E_MULTIPLE_CURRENTS,
    E_MULTIPLE_HEADS,
    E_NOTHING_APPLIED,
    E_UPGRADE_REQUIRED,
    E_NO_MODEL,
    E_MODEL_EXISTS,
    E_NO_LEGACY_STORE,
    E_LEGACY_STORE_EXISTS)


class MigrationException(Exception):
    exit_code = 1


class MultipleCurrentsException(MigrationException):
    exit_code = E_MULTIPLE_CURRENTS


class MultipleHeadsException(MigrationException):
    exit_code = E_MULTIPLE_HEADS


class NothingAppliedException(MigrationException):
    exit_code = E_NOTHING_APPLIED


class UpgradeRequiredException(MigrationException):
    exit_code = E_UPGRADE_REQUIRED


class NoModelException(MigrationException):
    exit_code = E_NO_MODEL


class ModelExistsException(MigrationException):
    exit_code = E_MODEL_EXISTS


class NoLegacyStoreException(MigrationException):
    exit_code = E_NO_LEGACY_STORE


class LegacyStoreExistsException(MigrationException):
    exit_code = E_LEGACY_STORE_EXISTS
