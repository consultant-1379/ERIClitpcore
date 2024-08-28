##############################################################################
# COPYRIGHT Ericsson 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

# error type constants
CARDINALITY_ERROR = "CardinalityError"
CHILD_NOT_ALLOWED_ERROR = "ChildNotAllowedError"
HEADER_NOT_ACCEPTABLE_ERROR = "HeaderNotAcceptableError"
INTERNAL_SERVER_ERROR = "InternalServerError"
SERVER_UNAVAILABLE_ERROR = "ServerUnavailableError"
ITEM_EXISTS_ERROR = "ItemExistsError"
INVALID_CHILD_TYPE_ERROR = "InvalidChildTypeError"
INVALID_LOCATION_ERROR = "InvalidLocationError"
INVALID_REF_ERROR = "InvalidReferenceError"
INVALID_REQUEST_ERROR = "InvalidRequestError"
INVALID_TYPE_ERROR = "InvalidTypeError"
INVALID_XML_ERROR = "InvalidXMLError"
METHOD_NOT_ALLOWED_ERROR = "MethodNotAllowedError"
MISSING_REQ_ITEM_ERROR = "MissingRequiredItemError"
MISSING_REQ_PROP_ERROR = "MissingRequiredPropertyError"
PROP_NOT_ALLOWED_ERROR = "PropertyNotAllowedError"
UNALLOCATED_PROP_ERROR = "UnallocatedPropertyError"
VALIDATION_ERROR = "ValidationError"
DO_NOTHING_PLAN_ERROR = "DoNothingPlanError"
CREDENTIALS_NOT_FOUND = "CredentialsNotFoundError"

# Task state constants
TASK_INITIAL = "Initial"
TASK_RUNNING = "Running"
TASK_STOPPED = "Stopped"
TASK_FAILED = "Failed"
TASK_SUCCESS = "Success"

# status constants
OK = 200
CREATED = 201
RESET = 205
NOT_FOUND = 404
METHOD_NOT_ALLOWED = 405
NOT_ACCEPTABLE = 406
CONFLICT = 409
UNPROCESSABLE = 422
INTERNAL_SERVER = 500
UNAUTHORIZED = 401
UNAVAILABLE = 503

# error type to status mapping
ERROR_STATUS_CODES = {
    CARDINALITY_ERROR: UNPROCESSABLE,
    CHILD_NOT_ALLOWED_ERROR: UNPROCESSABLE,
    HEADER_NOT_ACCEPTABLE_ERROR: NOT_ACCEPTABLE,
    INTERNAL_SERVER_ERROR: INTERNAL_SERVER,
    ITEM_EXISTS_ERROR: CONFLICT,
    INVALID_CHILD_TYPE_ERROR: UNPROCESSABLE,
    INVALID_LOCATION_ERROR: NOT_FOUND,
    INVALID_REF_ERROR: UNPROCESSABLE,
    INVALID_REQUEST_ERROR: UNPROCESSABLE,
    INVALID_TYPE_ERROR: UNPROCESSABLE,
    INVALID_XML_ERROR: UNPROCESSABLE,
    METHOD_NOT_ALLOWED_ERROR: METHOD_NOT_ALLOWED,
    MISSING_REQ_ITEM_ERROR: UNPROCESSABLE,
    MISSING_REQ_PROP_ERROR: UNPROCESSABLE,
    PROP_NOT_ALLOWED_ERROR: UNPROCESSABLE,
    UNALLOCATED_PROP_ERROR: UNPROCESSABLE,
    VALIDATION_ERROR: UNPROCESSABLE,
    DO_NOTHING_PLAN_ERROR: UNPROCESSABLE,
    CREDENTIALS_NOT_FOUND: UNPROCESSABLE,
    SERVER_UNAVAILABLE_ERROR: UNAVAILABLE
}

ERROR_MESSAGE_CODES = {
    METHOD_NOT_ALLOWED_ERROR: 'Operation not permitted'
}

# other constants
UPGRADE_SNAPSHOT_NAME = 'snapshot'
SNAPSHOT_BASE_PATH = '/snapshots'
UPGRADE_SNAPSHOT_PATH = "{0}/{1}".format(SNAPSHOT_BASE_PATH,
                                         UPGRADE_SNAPSHOT_NAME)
BASE_RPC_NO_ANSWER = 'No answer from node'
MAINTENANCE = 'maintenance'

PREPARE_FOR_RESTORE_ACTIONS = set([
    'remove_snapshot',
    'remove_certs',
    'set_to_initial',
    'remove_upgrade',
    'remove_manifests',
    'restore_default_manifests',
    'remove_last_plan'
])

CREATE_SNAPSHOT_PLAN = 'create_snapshot'
REMOVE_SNAPSHOT_PLAN = 'remove_snapshot'
RESTORE_SNAPSHOT_PLAN = 'restore_snapshot'
DEPLOYMENT_PLAN = 'Deployment'
REBOOT_PLAN = 'Reboot'

SNAPSHOT_PLANS = [
    CREATE_SNAPSHOT_PLAN,
    REMOVE_SNAPSHOT_PLAN,
    RESTORE_SNAPSHOT_PLAN,
]

LIVE_MODEL = "LAST_KNOWN_CONFIG"
SNAPSHOT_PLAN_MODEL = "SNAPSHOT_PLAN"
LAST_SUCCESSFUL_PLAN_MODEL = "LAST_SUCCESSFUL"
XML_BACKUP_MODEL = "XML_BACKUP"

MODEL_SERIALISATION_TYPES = (
    LIVE_MODEL,
    SNAPSHOT_PLAN_MODEL,
    LAST_SUCCESSFUL_PLAN_MODEL,
    XML_BACKUP_MODEL
)

NO_OUTAGE = "no outage"
OUTAGE_DETECTED = "outage detected"
OUTAGE_HANDLED = "outage handled"

CELERY_USER = "celery"
CELERY_GROUP = "celery"


class PrepareRestoreData(object):  # pylint: disable=too-few-public-methods
    """
    Class containing variables to be used when
    performing prepare-restore operations.
    """

    EXCLUDE_PATHS = ["/ms", "/plans", "/snapshots",
                     "/litp/maintenance", "/litp/import-iso",
                     "/litp/restore_model", "/litp/logging"]
