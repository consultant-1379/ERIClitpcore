import litp.core.constants as constants
from litp.core.validators import ValidationError
from litp.core.model_type import Reference
from litp.core.litp_logging import LitpLogger
from datetime import datetime
import re
import string
import rpm
import cherrypy
import contextlib

log = LitpLogger()


@contextlib.contextmanager
def set_exclude_nodes(obj, exclude_nodes_qi):
    try:
        obj.exclude_nodes = exclude_nodes_qi
        yield
    finally:
        obj.exclude_nodes = set()


def human_readable_request_type(request_method):
    operations = {
        "POST": "Create",
        "PUT": "Update",
        "GET": "Retrieve",
        "DELETE": "Remove"
    }
    return operations.get(request_method, "Unsupported")


def get_litp_version():
    core_list = get_litp_packages(subset=['ERIClitpcore'])
    if not core_list:
        return 'No version found'
    core = core_list[0]
    version, cxp, packager = \
        core['version'], core['cxp'], core['packager']
    return "{0} {1} {2}".format(version, cxp, packager)


def normalize_version(version):
    """
    Normalizes version for rstate calculation
    """
    maj_ver, min_ver, inc_ver = ('', '', '')
    values = version.split('.')
    if len(values) == 3:
        maj_ver, min_ver, inc_ver = values
        if '-' not in min_ver:
            if '-' in inc_ver:
                inc_ver = inc_ver.split('-')[0]
    elif len(values) == 2:
        maj_ver, min_ver = values
    return maj_ver, min_ver, inc_ver


def get_rstate(version):
    """
    Translates a version into an rstate
    """
    rstate_letters = sorted(set(string.uppercase)\
        - set(['I', 'O', 'P', 'Q', 'R', 'W']))

    maj_ver, min_ver, inc_ver = normalize_version(version)

    min_ver_prefix = ''
    min_ver_overflow = 0
    try:
        maj_ver = int(maj_ver)
        min_ver = int(min_ver)
        inc_ver = inc_ver if inc_ver == '' else int(inc_ver)
    except ValueError:
        log.trace.debug(
            "Error in version to rstate conversion: {0}".format(
                version
            )
        )
        return ""
    alph_length = len(rstate_letters)
    if min_ver >= alph_length:
        min_ver_overflow = (min_ver / alph_length)
        if min_ver_overflow >= 1:
            min_ver_prefix = rstate_letters[min_ver_overflow - 1]
        min_ver_overflow = min_ver % alph_length
        min_ver_prefix += rstate_letters[min_ver_overflow]
        min_ver = min_ver % alph_length
    min_ver = min_ver_prefix if min_ver_prefix\
                            else rstate_letters[min_ver]
    inc_ver = inc_ver if inc_ver == '' else str(inc_ver).zfill(2)
    return "R%s%s%s" % (maj_ver, min_ver, inc_ver)


def get_litp_packages(subset=None):
    """
    Queries the rpm db for installed packages starting
    as the first 4 chars with EXTR and ERIC .
    Based on: http://yum.baseurl.org/wiki/YumCodeSnippet/ListInstalledPkgs
    """
    litp_packages = []

    ts = rpm.TransactionSet()
    ts.setVSFlags((rpm._RPMVSF_NOSIGNATURES | rpm._RPMVSF_NODIGESTS))

    pkgs = [pkg for pkg in ts.dbMatch()  # pylint: disable=E1101
                if pkg[rpm.RPMTAG_NAME][:4] in ["EXTR", "ERIC"]]
    for pkg in pkgs:
        try:
            name, cxp = pkg[rpm.RPMTAG_NAME].split('_CXP')
            cxp = ''.join(['CXP', cxp])
        except ValueError:
            name, cxp = pkg[rpm.RPMTAG_NAME], ''

        version = pkg[rpm.RPMTAG_VERSION]
        rstate = pkg[rpm.RPMTAG_PACKAGER]
        if rstate is None or not rstate.startswith('R'):
            rstate = get_rstate(version)

        if not subset or subset and name in subset:
            log.trace.debug(
                "Found name: {0} cxp: {1} version: {2} packager: {3}".format(
                    name, cxp, version, rstate
                )
            )
            litp_packages.append({
                        "name": name,
                        "cxp": cxp,
                        "version": version,
                        "packager": rstate
                    })
    return litp_packages


def human_readable_timestamp(snapshot_obj):
    try:
        date_obj = datetime.fromtimestamp(float(snapshot_obj.timestamp))
        return date_obj.ctime()
    except:  # pylint: disable=W0702
        return ''


def update_maintenance(maintenance):
    if maintenance.get_property('enabled') == 'true':
        cherrypy.config.update({'maintenance': True})
    else:
        cherrypy.config.update({'maintenance': False})


def get_maintenance():
    return cherrypy.config.get('maintenance', False)


def get_db_availability():
    return cherrypy.config.get('db_available', True)


def set_db_availability(status):
    cherrypy.config.update({'db_available': status})
    if not status:
        try:
            cherrypy.config['execution_manager'].outage_handler()
        except KeyError:
            pass
        log.event.warning('Database unavailable!')


class FieldManager(object):

    def get_context(self, field_name, field_item):
        field_map = {
            'RefCollection': self.get_ref_collection_context,
            'Collection': self.get_collection_context,
            'Reference': self.get_reference_context,
            'Property': self.get_property_context,
            'Child': self.get_child_context,
            'Miscellaneous': self.get_misc_context,
        }

        func = field_map.get(field_item.__class__.__name__, None)
        if func is None:
            func = field_map['Miscellaneous']

        return func(field_name, field_item)

    def get_collection_context(self, field_name, field_item):
        context = {
            "collection-of": {
                "href": "/item-types/%s" % field_item.item_type_id
            }
        }
        return context

    def get_ref_collection_context(self, field_name, field_item):
        context = {
            "ref-collection-of": {
                "href": "/item-types/%s" % field_item.item_type_id
            }
        }
        return context

    def get_reference_context(self, field_name, field_item):
        context = {
            '_links': {}
        }
        if isinstance(field_item, Reference):
            context = {
                'reference-to': {
                    'href': '/item-types/%s' % field_item.item_type_id
                }
            }
        return context

    def get_property_context(self, field_name, field_item):
        context = {
            'property-type': {
                'href': '/property-types/%s' %
                    field_item.prop_type.property_type_id,
            }
        }
        return context

    def get_child_context(self, field_name, field_item):
        context = {
            "self": {
                "href": "/item-types/%s" % field_item.item_type_id
            }
        }
        return context

    def get_misc_context(self, field_name, field_item):
        context = {
            "self": {
                "href": "/item-types/%s" % field_item.item_type_id
            }
        }
        return context


class ItemPayloadValidator(object):

    def __init__(self, json_data, item_path):
        self.body_dict = json_data
        self.item_path = item_path

    def validate_id(self):
        validation_errors = []
        if 'id' not in self.body_dict:
            validation_errors.append(
                ValidationError(
                    item_path=self.item_path,
                    error_message="Invalid value for argument ID ('None')",
                    error_type=constants.INVALID_REQUEST_ERROR)
            )
        return validation_errors

    def validate_item_type(self):
        validation_errors = []
        conditions = [
            "type" in self.body_dict,
            "inherit" in self.body_dict
        ]

        if not any(conditions) or all(conditions):
            message = "Must specify either property type or property link"
            validation_errors.append(ValidationError(
                item_path=self.item_path,
                error_message=message,
                error_type=constants.INVALID_REQUEST_ERROR))

        return validation_errors

    def validate(self):
        validation_errors = []
        validation_errors.extend(self.validate_id())
        validation_errors.extend(self.validate_item_type())
        return [err.to_dict() for err in validation_errors]


class PlanPayloadValidator(object):
    '''
    called to validate creating a plan
    '''
    def __init__(self, json_data):
        self.body_dict = json_data

    def validate_id(self):
        validation_errors = []
        plan_id = self.body_dict.get("id")
        if plan_id != "plan":
            validation_errors.append(
                ValidationError(
                    item_path='/plans',
                    error_message=("Invalid value for argument ID :%s" %
                                   plan_id),
                    error_type=constants.INVALID_REQUEST_ERROR)
            )
        return validation_errors

    def validate_type(self):
        validation_errors = []
        plan_type = self.body_dict.get('type', None)
        if plan_type not in ("plan", "reboot_plan"):
            msg = "Must specify type as 'plan' or 'reboot_plan'"
            validation_errors.append(
                ValidationError(
                    item_path='/plans',
                    error_message=msg,
                    error_type=constants.INVALID_REQUEST_ERROR)
            )
        return validation_errors

    def validate_no_lock_tasks(self):
        validation_errors = []
        lock_value = self.body_dict.get("no-lock-tasks", '')
        lock_list = self.body_dict.get("no-lock-tasks-list", [])
        pattern = re.compile(r'^(true|false|True|False)$')
        if lock_value and pattern.match(lock_value) is None:
            msg = (
                "Invalid value for no-lock-tasks specified: '%s'" % lock_value
            )
            validation_errors.append(
                ValidationError(
                    item_path="/plans/plan",
                    error_message=msg,
                    error_type=constants.INVALID_REQUEST_ERROR
                )
            )
        pattern = re.compile(r'^(true|True)$')
        if len(lock_list) > 0 and pattern.match(lock_value) is None:
            msg = (
            "Invalid value for no-lock-tasks when no-lock-tasks-list "
            "specified: '%s'" % lock_value
            )
            validation_errors.append(
                ValidationError(
                    item_path="/plans/plan",
                    error_message=msg,
                    error_type=constants.INVALID_REQUEST_ERROR
                )
            )
        return validation_errors

    def validate_properties(self):
        validation_errors = []
        for prop in self.body_dict.get('properties', {}):
            msg = "Invalid property '%s'" % prop
            if prop == "state":
                msg = "Invalid property '%s' for plan create" % prop
            validation_errors.append(
                ValidationError(property_name=prop, error_message=msg)
            )
        return validation_errors

    def validate(self):
        validation_errors = []
        validation_errors.extend(self.validate_id())
        validation_errors.extend(self.validate_type())
        validation_errors.extend(self.validate_no_lock_tasks())
        validation_errors.extend(self.validate_properties())
        return [err.to_dict() for err in validation_errors]


class PlanValidator(object):

    def __init__(self, plan, plan_id):
        self.plan = plan
        self.plan_id = plan_id

    def validate_id(self):
        validation_errors = []
        if self.plan_id != 'plan':
            validation_errors.append(
                ValidationError(
                    item_path='/plans/' + self.plan_id,
                    error_message=("Item not found"),
                    error_type=constants.INVALID_LOCATION_ERROR)
            )
        return validation_errors

    def validate_plan(self):
        validation_errors = []
        if self.plan is None:
            msg = "Plan does not exist"
            validation_errors.append(
                ValidationError(
                    item_path='/plans/',
                    error_message=msg,
                    error_type=constants.INVALID_LOCATION_ERROR)
            )
        return validation_errors

    def validate(self):
        validation_errors = []
        validation_errors.extend(self.validate_id())
        if not validation_errors:
            validation_errors.extend(self.validate_plan())
        return [err.to_dict() for err in validation_errors]


class PhaseValidator(PlanValidator):
    def __init__(self, plan, plan_id, phase_id):
        super(PhaseValidator, self).__init__(plan, plan_id)
        self.phase_id = phase_id

    def validate_phase(self):
        validation_errors = []
        validation_errors.extend(self.validate_id())
        validation_errors.extend(self.validate_plan())
        if not validation_errors:
            try:
                phase = self.plan.get_phase(int(self.phase_id) - 1)
            except ValueError:
                phase = None

            if phase is None:
                msg = "Invalid phase id :%s" % self.phase_id
                validation_errors.append(
                    ValidationError(
                        item_path='/plans/plan/phases/%s' % self.phase_id,
                        error_message=msg,
                        error_type=constants.INVALID_LOCATION_ERROR
                    ))
        return validation_errors

    def validate(self):
        validation_errors = self.validate_phase()
        return [err.to_dict() for err in validation_errors]


class TaskValidator(PhaseValidator):
    def __init__(self, plan, plan_id, phase_id, task_id):
        super(TaskValidator, self).__init__(plan, plan_id, phase_id)
        self.task_id = task_id

    def validate_task(self):
        validation_errors = self.validate_phase()
        if not validation_errors:
            task = self.plan.get_task(int(self.phase_id) - 1, self.task_id)
            if task is None:
                msg = "Invalid task id :%s" % self.task_id
                validation_errors.append(
                    ValidationError(
                        item_path=(
                            '/plans/%s/phases/%s/tasks/%s' %
                            (self.plan_id, self.phase_id, self.task_id)),
                        error_message=msg,
                        error_type=constants.INVALID_LOCATION_ERROR
                    )
                )
        return validation_errors

    def validate(self):
        validation_errors = self.validate_task()
        return [err.to_dict() for err in validation_errors]


class UpdatePlanPayloadValidator(PlanValidator):
    def __init__(self, plan, plan_id, json_data):
        super(UpdatePlanPayloadValidator, self).__init__(plan, plan_id)
        self.body_dict = json_data

    def validate_state(self):
        validation_errors = []
        item_properties = self.body_dict.get('properties', {})
        if item_properties:
            state = item_properties.get("state")
            if state not in ['running', 'stopped']:
                error_message = "Invalid state specified"
                if state is None:
                    error_message = "Property 'state' must be specified"
                validation_errors.append(
                    ValidationError(
                        item_path='/plans/plan',
                        error_message=error_message,
                        error_type=constants.INVALID_REQUEST_ERROR)
                )
        else:
            msg = "Properties must be specified for update"
            validation_errors.append(
                ValidationError(
                    item_path='/plans/plan',
                    error_message=msg,
                    error_type=constants.INVALID_REQUEST_ERROR
                ))
        return validation_errors

    def _validate_plan_state(self):
        validation_errors = []
        validation_errors.extend(self.validate_id())
        validation_errors.extend(self.validate_plan())
        return validation_errors

    def validate(self):
        validation_errors = self.validate_state()
        validation_errors.extend(self._validate_plan_state())
        return [err.to_dict() for err in validation_errors]
