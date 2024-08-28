import unittest

import yum
import rpm
from datetime import datetime

from mock import MagicMock, patch, PropertyMock

from litp.core import constants
from litp.service import utils
from base import MethodCallLogger
from base import Mock, MockPlan, MockTask


class TestFieldManager(unittest.TestCase):

    def setUp(self):
        self.item = self._setup_item()

        self.field_name = 'some_field_name'
        self.field_manager = utils.FieldManager()

    def tearDown(self):
        self.item.__class__.__name__ = 'Mock'

    def _setup_item(self):
        item = Mock()
        item.required = True
        item.default = True
        item.item_type_id = 'some_type_id'
        item.item_description = 'item description'
        item.properties = {}
        item.min_count = 0
        item.max_count = 5
        item.prop_description = 'property description'
        item.prop_type = Mock()
        item.prop_type.property_type_id = 'some_property_id'
        item.prop_type.regex = '.*'
        return item

    def test_collection_context(self):
        self.item.__class__.__name__ = 'RefCollection'
        context = self.field_manager.get_context(
            self.field_name, self.item
        )

        expected_context = {
            'ref-collection-of': {
                'href': '/item-types/some_type_id'
            }
        }
        self.assertEquals(context, expected_context)

    def test_reference_context(self):
        self.item.__class__.__name__ = 'Reference'
        context = self.field_manager.get_context(
            self.field_name, self.item
        )

        expected_context = {
            '_links': {}
        }

        self.assertEquals(context, expected_context)

    def test_property_context(self):
        self.item.__class__.__name__ = 'Property'
        context = self.field_manager.get_context(
            self.field_name, self.item
        )

        expected_context = {
            'property-type': {
                'href': '/property-types/some_property_id'
            }
        }

        self.assertEquals(context, expected_context)

    def test_child_context(self):
        self.item.__class__.__name__ = 'Child'
        context = self.field_manager.get_context(
            self.field_name, self.item
        )

        expected_context = {
            'self': {'href': '/item-types/some_type_id'}
        }

        self.assertEquals(context, expected_context)

    def test_misc_context(self):
        context = self.field_manager.get_context(
            self.field_name, self.item
        )

        expected_context = {
            'self': {'href': '/item-types/some_type_id'}
        }

        self.assertEquals(context, expected_context)

    def test_human_readable_timestamp(self):
        # hard to say what's the best place for this unit test
        s = MagicMock()
        s.timestamp = 1399969162.062561
        self.assertNotEquals('',
                          utils.human_readable_timestamp(s))
        s.timestamp = 1399969162
        self.assertNotEquals('',
                          utils.human_readable_timestamp(s))
        s.timestamp = '1399969162.062561'
        self.assertNotEquals('',
                          utils.human_readable_timestamp(s))
        s.timestamp = ''
        self.assertEquals('',
                          utils.human_readable_timestamp(s))
        s.timestamp = None
        self.assertEquals('',
                          utils.human_readable_timestamp(s))


class TestItemPayloadValidator(unittest.TestCase):

    def setUp(self):
        self.validator = utils.ItemPayloadValidator({}, 'some_path')

    def test_validate_missing_id(self):
        validation_errors = self.validator.validate_id()
        self.assertEquals(len(validation_errors), 1)
        err = validation_errors[0]
        self.assertEquals(err.item_path, self.validator.item_path)
        self.assertEquals(err.error_type, constants.INVALID_REQUEST_ERROR)
        self.assertEquals(
            err.error_message, "Invalid value for argument ID ('None')"
        )

    def test_validate_id(self):
        self.validator.body_dict = {'id': 'foo'}
        validation_errors = self.validator.validate_id()
        self.assertEquals(len(validation_errors), 0)

    def test_validate_missing_type(self):
        validation_errors = self.validator.validate_item_type()
        self.assertEquals(len(validation_errors), 1)
        err = validation_errors[0]
        self.assertEquals(err.item_path, self.validator.item_path)
        self.assertEquals(err.error_type, constants.INVALID_REQUEST_ERROR)
        self.assertEquals(
            err.error_message,
            "Must specify either property type or property link"
        )

    def test_validate_type_and_link(self):
        self.validator.body_dict = {
            'type': 'some type',
            'link': 'some link',
            'inherit': 'some path'
        }
        validation_errors = self.validator.validate_item_type()
        self.assertEquals(len(validation_errors), 1)
        err = validation_errors[0]
        self.assertEquals(err.item_path, self.validator.item_path)
        self.assertEquals(err.error_type, constants.INVALID_REQUEST_ERROR)
        self.assertEquals(
            err.error_message,
            "Must specify either property type or property link"
        )

    def test_validate_type(self):
        self.validator.body_dict = {
            'type': 'some type',
        }
        validation_errors = self.validator.validate_item_type()
        self.assertEquals(len(validation_errors), 0)

    def test_validate(self):
        validation_errors = self.validator.validate()
        self.assertEquals(len(validation_errors), 2)
        self.assertTrue(
            all([isinstance(err, dict) for err in validation_errors])
        )

        self.validator.body_dict.update({'id': 'my id'})
        validation_errors = self.validator.validate()
        self.assertEquals(len(validation_errors), 1)

        self.validator.body_dict.update({'type': 'some type'})
        validation_errors = self.validator.validate()
        self.assertEquals(len(validation_errors), 0)


class TestPlanPayloadValidator(unittest.TestCase):

    def setUp(self):
        self.validator = utils.PlanPayloadValidator({})

    def test_validate_missing_id(self):
        validation_errors = self.validator.validate_id()
        self.assertEquals(len(validation_errors), 1)
        err = validation_errors[0]
        self.assertEquals(err.item_path, '/plans')
        self.assertEquals(err.error_type, constants.INVALID_REQUEST_ERROR)
        self.assertEquals(
            err.error_message,
            "Invalid value for argument ID :None"
        )

    def test_validate_wrong_id(self):
        self.validator.body_dict = {'id': 'some plan'}
        validation_errors = self.validator.validate_id()
        self.assertEquals(1, len(validation_errors))
        err = validation_errors[0]
        self.assertEquals(err.item_path, '/plans')
        self.assertEquals(err.error_type, constants.INVALID_REQUEST_ERROR)
        self.assertEquals(
            err.error_message,
            "Invalid value for argument ID :some plan"
        )

    def test_validate_id(self):
        self.validator.body_dict = {'id': 'plan'}
        validation_errors = self.validator.validate_id()
        self.assertEquals(len(validation_errors), 0)

    def test_validate_missing_type(self):
        validation_errors = self.validator.validate_type()
        self.assertEquals(len(validation_errors), 1)
        err = validation_errors[0]
        self.assertEquals(err.item_path, '/plans')
        self.assertEquals(err.error_type, constants.INVALID_REQUEST_ERROR)
        self.assertEquals(
            err.error_message,
            "Must specify type as 'plan' or 'reboot_plan'"
        )

    def test_validate_wrong_type(self):
        self.validator.body_dict = {'type': 'some plan'}
        validation_errors = self.validator.validate_type()
        self.assertEquals(len(validation_errors), 1)
        err = validation_errors[0]
        self.assertEquals(err.item_path, '/plans')
        self.assertEquals(err.error_type, constants.INVALID_REQUEST_ERROR)
        self.assertEquals(
            err.error_message,
            "Must specify type as 'plan' or 'reboot_plan'"
        )

    def test_validate_type(self):
        self.validator.body_dict = {'type': 'plan'}
        validation_errors = self.validator.validate_type()
        self.assertEquals(len(validation_errors), 0)

    def test_validate(self):
        validation_errors = self.validator.validate()
        self.assertEquals(len(validation_errors), 2)
        self.assertTrue(
            all([isinstance(err, dict) for err in validation_errors])
        )

        self.validator.body_dict.update({'id': 'plan'})
        validation_errors = self.validator.validate()
        self.assertEquals(len(validation_errors), 1)

        self.validator.body_dict.update({'type': 'plan'})
        validation_errors = self.validator.validate()
        self.assertEquals(len(validation_errors), 0)


class TestPlanValidator(unittest.TestCase):

    def setUp(self):
        self.validator = utils.PlanValidator(plan=None, plan_id='')

    def test_validate_missing_id(self):
        validation_errors = self.validator.validate_id()
        self.assertEquals(len(validation_errors), 1)
        err = validation_errors[0]
        self.assertEquals(err.item_path, '/plans/')
        self.assertEquals(err.error_type, constants.INVALID_LOCATION_ERROR)
        self.assertEquals(
            err.error_message, "Item not found"
        )

    def test_validate_wrong_id(self):
        self.validator.plan_id = 'some_id'
        validation_errors = self.validator.validate_id()
        self.assertEquals(len(validation_errors), 1)
        err = validation_errors[0]
        self.assertEquals(err.item_path, '/plans/some_id')
        self.assertEquals(err.error_type, constants.INVALID_LOCATION_ERROR)
        self.assertEquals(
            err.error_message, "Item not found"
        )

    def test_validate_id(self):
        self.validator.plan_id = 'plan'
        validation_errors = self.validator.validate_id()
        self.assertEquals(len(validation_errors), 0)

    def test_validate_missing_plan(self):
        validation_errors = self.validator.validate_plan()
        self.assertEquals(len(validation_errors), 1)
        err = validation_errors[0]
        self.assertEquals(err.item_path, '/plans/')
        self.assertEquals(err.error_type, constants.INVALID_LOCATION_ERROR)
        self.assertEquals(
            err.error_message,
            "Plan does not exist"
        )

    def test_validate_plan(self):
        self.validator.plan = Mock()
        validation_errors = self.validator.validate_plan()
        self.assertEquals(len(validation_errors), 0)

    def test_validate(self):
        validation_errors = self.validator.validate()
        self.assertEquals(len(validation_errors), 1)
        self.assertTrue(
            all([isinstance(err, dict) for err in validation_errors])
        )

        self.validator.plan_id = 'plan'
        validation_errors = self.validator.validate()
        self.assertEquals(len(validation_errors), 1)

        self.validator.plan = Mock()
        validation_errors = self.validator.validate()
        self.assertEquals(len(validation_errors), 0)


class TestPhaseValidator(unittest.TestCase):

    def setUp(self):
        self.validator = utils.PhaseValidator(
            plan=None, plan_id='', phase_id=''
        )

    def test_validate_phase_no_plan(self):
        validation_errors = self.validator.validate_phase()
        self.assertEquals(len(validation_errors), 2)

    def test_validate_phase_invalid_plan_id(self):
        self.validator.plan = MockPlan()
        validation_errors = self.validator.validate_phase()
        self.assertEquals(len(validation_errors), 1)

    def test_validate_phase_invalid_phase_id(self):
        self.validator.plan_id = 'plan'
        self.validator.plan = MockPlan()
        self.validator.plan._phases = [[Mock()]]

        self.validator.phase_id = 'some_phase_id'
        validation_errors = self.validator.validate_phase()
        self.assertEquals(len(validation_errors), 1)
        err = validation_errors[0]
        self.assertEquals(err.item_path, '/plans/plan/phases/some_phase_id')
        self.assertEquals(err.error_type, constants.INVALID_LOCATION_ERROR)
        self.assertEquals(
            err.error_message,
            "Invalid phase id :some_phase_id"
        )

    def test_validate_phase(self):
        self.validator.plan_id = 'plan'
        self.validator.plan = MockPlan()
        self.validator.plan._phases = [[Mock()]]

        self.validator.phase_id = '1'
        validation_errors = self.validator.validate_phase()
        self.assertEquals(len(validation_errors), 0)

    def test_validate(self):
        validation_errors = self.validator.validate()
        self.assertEquals(len(validation_errors), 2)
        self.assertTrue(
            all([isinstance(err, dict) for err in validation_errors])
        )

        self.validator.plan_id = 'plan'
        validation_errors = self.validator.validate()
        self.assertEquals(len(validation_errors), 1)

        self.validator.plan = MockPlan()
        self.validator.plan._phases = [[Mock()]]
        validation_errors = self.validator.validate()
        self.assertEquals(len(validation_errors), 1)

        self.validator.phase_id = '1'
        validation_errors = self.validator.validate()
        self.assertEquals(len(validation_errors), 0)


class TestTaskValidator(unittest.TestCase):

    def setUp(self):
        self.validator = utils.TaskValidator(plan=None, plan_id='',
                                             phase_id='', task_id='')

    def _setup_valid_phase(self):
        self.validator.plan_id = 'plan'
        self.validator.phase_id = '1'
        self.validator.task_id = 'my_task'
        self.validator.plan = MockPlan()
        self.validator.plan._phases = [[]]

    def _setup_valid_task(self):
        self._setup_valid_phase()
        task = MockTask()
        self.validator.plan._phases[0].append(task)

    def test_validate_task_calls_parent_validation(self):
        self.validator.validate_phase = MethodCallLogger(
            self.validator.validate_phase
        )
        validation_errors = self.validator.validate_task()
        self.assertEquals(len(validation_errors), 2)
        self.assertTrue(self.validator.validate_phase.was_called)

    def test_validate_no_task(self):
        self._setup_valid_phase()

        validation_errors = self.validator.validate_task()
        self.assertEquals(len(validation_errors), 1)
        err = validation_errors[0]
        self.assertEquals(err.item_path, '/plans/plan/phases/1/tasks/my_task')
        self.assertEquals(err.error_type, constants.INVALID_LOCATION_ERROR)
        self.assertEquals(err.error_message, "Invalid task id :my_task")

    def test_validate_task(self):
        self._setup_valid_task()
        self.validator.task_id = 'my_unique_id'

        validation_errors = self.validator.validate_task()
        self.assertEquals(len(validation_errors), 0)

    def test_validate(self):
        self._setup_valid_task()
        self.validator.validate_task = MethodCallLogger(
            self.validator.validate_task
        )

        validation_errors = self.validator.validate()
        self.assertTrue(self.validator.validate_task.was_called)
        self.assertEquals(len(validation_errors), 1)

        self.validator.task_id = 'my_unique_id'
        validation_errors = self.validator.validate()
        self.assertTrue(self.validator.validate_task.was_called)
        self.assertEquals(len(validation_errors), 0)


class TestUpdatePlanPayloadValidator(unittest.TestCase):

    def setUp(self):
        self.validator = utils.UpdatePlanPayloadValidator(
            plan=None, plan_id='', json_data={}
        )

    def test_invalid_properties(self):
        validation_errors = self.validator.validate_state()
        self.assertEquals(len(validation_errors), 1)

        err = validation_errors[0]
        self.assertEquals(err.item_path, '/plans/plan')
        self.assertEquals(err.error_type, constants.INVALID_REQUEST_ERROR)
        self.assertEquals(err.error_message,
                          "Properties must be specified for update")

        self.validator.body_dict = {"properties": {'state': 'my state'}}
        validation_errors = self.validator.validate_state()
        self.assertEquals(len(validation_errors), 1)
        err = validation_errors[0]
        self.assertEquals(err.item_path, '/plans/plan')
        self.assertEquals(err.error_type, constants.INVALID_REQUEST_ERROR)
        self.assertEquals(err.error_message, "Invalid state specified")

        self.validator.body_dict = {"properties": {'prop': 'my prop'}}
        validation_errors = self.validator.validate_state()
        self.assertEquals(len(validation_errors), 1)
        err = validation_errors[0]
        self.assertEquals(err.item_path, '/plans/plan')
        self.assertEquals(err.error_type, constants.INVALID_REQUEST_ERROR)
        self.assertEquals(err.error_message,
                          "Property 'state' must be specified")

    def test_validate_state(self):
        self.validator.body_dict = {"properties": {'state': 'running'}}
        validation_errors = self.validator.validate_state()
        self.assertEquals(len(validation_errors), 0)

    def test_validate_plan_state_parent_validation(self):
        self.validator.validate_id = MethodCallLogger(
            self.validator.validate_id)
        self.validator.validate_plan = MethodCallLogger(
            self.validator.validate_plan)

        self.validator._validate_plan_state()
        self.assertTrue(self.validator.validate_id.was_called)
        self.assertTrue(self.validator.validate_plan.was_called)

    def test_validate_plan_state(self):
        self.validator.plan = MockPlan()
        self.validator.plan_id = 'plan'

        self.validator.plan.running = False
        self.validator.plan.valid = True
        validation_errors = self.validator._validate_plan_state()
        self.assertEquals(len(validation_errors), 0)

    def test_validate(self):
        self.validator.validate_state = MethodCallLogger(
            self.validator.validate_state)

        validation_errors = self.validator.validate()

        self.assertTrue(self.validator.validate_state.was_called)
        self.assertEquals(len(validation_errors), 3)
        self.assertTrue(
            all([isinstance(err, dict) for err in validation_errors]))


installed_packages = [
        {'name': 'ERIClitpbmcapi_CXP9030611', 'version': '1.8.1'},
        {'name': 'ERIClitpbootmgrapi_CXP9030523', 'version': '1.10.1'},
        {'version': '1.13.1', 'name': 'ERIClitpbootmgr_CXP9030515'},
        {'version': '1.9.3', 'name': 'ERIClitpcbaapi_CXP9030830'},
        {'version': '1.11.1', 'name': 'ERIClitpcfg_CXP9030421'},
        {'version': '1.14.5', 'name': 'ERIClitpcli_CXP9030420'},
        {'version': '1.14.27', 'name': 'ERIClitpcore_CXP9030418'},
        {'version': '1.13.173', 'name': 'ERIClitpdocs_second_CXP9030557'},
        {'version': '1.20.173', 'name': 'ERIClitpdocs_CXP9030557'},
        {'version': '1.22.3', 'name': 'ERIClitpcli_CXP9030420'},
        {'version': '1.22', 'name': 'ERIClitpclitwo_CXP9030420'},
        {'version': '1.22.3-4', 'name': 'ERIClitpclihyphen_CXP9030420'},
        {'version': '1.22-5', 'name': 'ERIClitpclihyphentwo_CXP9030420'},
        {'version': '1.22-5.22-5', 'name': 'ERIClitpclihyphenthree_CXP9030420'},
        {'version': '1.22-5.5', 'name': 'ERIClitpclihyphenfour_CXP9030420'},
        {'version': '1.40.1', 'name': 'ERIClitpfourty_CXP9030421'},
]

class TestGetLitpVersionInfo(unittest.TestCase):

    def _setup_ts(self, get_list_callable):
        tsmock = MagicMock()
        tsmock.dbMatch = MagicMock()
        tsmock.dbMatch.side_effect = get_list_callable
        rpm.TransactionSet = MagicMock(return_value=tsmock)

    def _createMockPackage(self, name, version, packager=''):
        pkg = {}
        pkg[rpm.RPMTAG_NAME] = name
        pkg[rpm.RPMTAG_VERSION] = version
        pkg[rpm.RPMTAG_PACKAGER] = packager
        return pkg

    def get_package_list_negative(self):
        packages = []
        pkg = self._createMockPackage("Boguspackage", '12.13.14')
        packages.append(pkg)
        return packages


    def get_package_list(self, return_list=installed_packages):
        packages = []
        for pkg in return_list:
            pkg = self._createMockPackage(pkg['name'], pkg['version'])
            packages.append(pkg)
        return packages

    def test_get_litp_version(self):
        self._setup_ts(self.get_package_list)
        self.assertEqual('1.14.27 CXP9030418 R1T27',
                            utils.get_litp_version())

    def test_get_rstate(self):
        self.assertEqual('R1T27', utils.get_rstate('1.14.27'))
        self.assertEqual('R1G02', utils.get_rstate('1.6.2'))
        self.assertEqual('R1G03', utils.get_rstate('1.6.3'))
        self.assertEqual('R2G02', utils.get_rstate('2.6.2'))
        self.assertEqual('R2AZ02', utils.get_rstate('2.39.2'))
        self.assertEqual('R2AZ39', utils.get_rstate('2.39.39'))
        self.assertEqual('R2BA02', utils.get_rstate('2.40.2'))
        self.assertEqual('R2DA02', utils.get_rstate('2.80.2'))
        self.assertEqual('R80H02', utils.get_rstate('80.7.2'))
        #after v419
        # min_ver_prefix = rstate_letters[min_ver_overflow - 1]
        # IndexError: list index out of range
        self.assertEqual('R2ZZ02', utils.get_rstate('2.419.2'))

    def test_get_litp_version_negative(self):
        self._setup_ts(self.get_package_list_negative)
        self.assertEqual('No version found',
                         utils.get_litp_version())

    def test_get_litp_packages(self):
        self._setup_ts(self.get_package_list)
        self.assertEqual([
          {'cxp': 'CXP9030611', 'packager': 'R1J01', 'version': '1.8.1', 'name': 'ERIClitpbmcapi'},
          {'cxp': 'CXP9030523', 'packager': 'R1L01', 'version': '1.10.1', 'name': 'ERIClitpbootmgrapi'},
          {'cxp': 'CXP9030515', 'packager': 'R1S01', 'version': '1.13.1', 'name': 'ERIClitpbootmgr'},
          {'cxp': 'CXP9030830', 'packager': 'R1K03', 'version': '1.9.3', 'name': 'ERIClitpcbaapi'},
          {'cxp': 'CXP9030421', 'packager': 'R1M01', 'version': '1.11.1', 'name': 'ERIClitpcfg'},
          {'cxp': 'CXP9030420', 'packager': 'R1T05', 'version': '1.14.5', 'name': 'ERIClitpcli'},
          {'cxp': 'CXP9030418', 'packager': 'R1T27', 'version': '1.14.27', 'name': 'ERIClitpcore'},
          {'cxp': 'CXP9030557', 'packager': 'R1S173', 'version': '1.13.173', 'name': 'ERIClitpdocs_second'},
          {'cxp': 'CXP9030557', 'packager': 'R1AA173', 'version': '1.20.173', 'name': 'ERIClitpdocs'},
          {'cxp': 'CXP9030420', 'packager': 'R1AC03','version': '1.22.3', 'name': 'ERIClitpcli'},
          {'cxp': 'CXP9030420', 'packager': 'R1AC','version': '1.22', 'name': 'ERIClitpclitwo'},
          {'cxp': 'CXP9030420', 'packager': 'R1AC03','version': '1.22.3-4', 'name': 'ERIClitpclihyphen'},
          {'cxp': 'CXP9030420', 'packager': '','version': '1.22-5', 'name': 'ERIClitpclihyphentwo'},
          {'cxp': 'CXP9030420', 'packager': '','version': '1.22-5.22-5', 'name': 'ERIClitpclihyphenthree'},
          {'cxp': 'CXP9030420', 'packager': '','version': '1.22-5.5', 'name': 'ERIClitpclihyphenfour'},
          {'cxp': 'CXP9030421', 'packager': 'R1BA01','version': '1.40.1', 'name': 'ERIClitpfourty'},
                          ],
                         utils.get_litp_packages())
        self._setup_ts(self.get_package_list_negative)
        self.assertEqual('No version found', utils.get_litp_version())

    def test_get_litp_packages_negative(self):
        self._setup_ts(self.get_package_list_negative)
        self.assertEqual([], utils.get_litp_packages())

    def test_get_litp_packages_subsets(self):
        self._setup_ts(self.get_package_list)
        self.assertEqual([
          {'cxp': 'CXP9030611', 'packager': 'R1J01', 'version': '1.8.1', 'name': 'ERIClitpbmcapi'},
          {'cxp': 'CXP9030523', 'packager': 'R1L01', 'version': '1.10.1', 'name': 'ERIClitpbootmgrapi'},
          {'cxp': 'CXP9030515', 'packager': 'R1S01', 'version': '1.13.1', 'name': 'ERIClitpbootmgr'},
          {'cxp': 'CXP9030830', 'packager': 'R1K03', 'version': '1.9.3', 'name': 'ERIClitpcbaapi'},
          {'cxp': 'CXP9030421', 'packager': 'R1M01', 'version': '1.11.1', 'name': 'ERIClitpcfg'},
          {'cxp': 'CXP9030420', 'packager': 'R1T05', 'version': '1.14.5', 'name': 'ERIClitpcli'},
          {'cxp': 'CXP9030418', 'packager': 'R1T27', 'version': '1.14.27', 'name': 'ERIClitpcore'},
          {'cxp': 'CXP9030557', 'packager': 'R1S173', 'version': '1.13.173', 'name': 'ERIClitpdocs_second'},
          {'cxp': 'CXP9030557', 'packager': 'R1AA173', 'version': '1.20.173', 'name': 'ERIClitpdocs'},
          {'cxp': 'CXP9030420', 'packager': 'R1AC03','version': '1.22.3', 'name': 'ERIClitpcli'},
          {'cxp': 'CXP9030420', 'packager': 'R1AC','version': '1.22', 'name': 'ERIClitpclitwo'},
          {'cxp': 'CXP9030420', 'packager': 'R1AC03','version': '1.22.3-4', 'name': 'ERIClitpclihyphen'},
          {'cxp': 'CXP9030420', 'packager': '','version': '1.22-5', 'name': 'ERIClitpclihyphentwo'},
          {'cxp': 'CXP9030420', 'packager': '','version': '1.22-5.22-5', 'name': 'ERIClitpclihyphenthree'},
          {'cxp': 'CXP9030420', 'packager': '','version': '1.22-5.5', 'name': 'ERIClitpclihyphenfour'},
          {'cxp': 'CXP9030421', 'packager': 'R1BA01','version': '1.40.1', 'name': 'ERIClitpfourty'},
                          ],
                         utils.get_litp_packages([]))
        self.assertEqual([{'cxp': 'CXP9030418', 'packager': 'R1T27', 'version': '1.14.27', 'name': 'ERIClitpcore'}],
                         utils.get_litp_packages(['ERIClitpcore']))
        self.assertEqual([],
                         utils.get_litp_packages(['what is this i dont even']))
