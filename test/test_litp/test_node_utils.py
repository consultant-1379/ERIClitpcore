##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

from unittest import TestCase
import time
from mock import MagicMock, patch
from litp.core.node_utils import (_wait_for_callback, _check_node,
                            _check_node_down, wait_for_node, wait_for_node_down, wait_for_node_puppet_applying_catalog_valid)
from litp.core.rpc_commands import run_rpc_command
from litp.core.exceptions import CallbackExecutionException
from litp.core.exceptions import PlanStoppedException


class TestCallbackApi(TestCase):

    @patch('litp.core.node_utils._get_current_time')
    def test_wait_for_callback(self, patched_time):

        mock_api = MagicMock()
        test_callback = MagicMock(return_value=True)
        mock_api.is_running.return_value = False
        _wait_for_callback(mock_api, "test_message", False, test_callback, 3600)
        #check that exception is NOT thrown
        self.assertTrue(True)

        test_callback = MagicMock(return_value=False)
        mock_api.is_running.return_value = False
        self.assertRaises(PlanStoppedException,
                          _wait_for_callback, mock_api,
                          "test_message",  True, test_callback, 3600)

        patched_time.side_effect = [0.0, 36.0, 360.0, 3600.0]
        old_time_sleep = time.sleep
        time.sleep = MagicMock()
        mock_api.is_running.return_value = True
        self.assertRaises(CallbackExecutionException,
                          _wait_for_callback, mock_api,
                          "test_message",  False, test_callback, 3600)

        time.sleep = old_time_sleep

    @patch('litp.core.node_utils.run_rpc_command')
    def test__check_node(self, test_patch):
        test_patch.return_value = {"test_hostname": {"data": {"status": "idling"}, "errors": ""}}

        result = _check_node(["test_hostname"], False, True)
        self.assertTrue(result)

        test_patch.return_value = {"test_hostname": {"data": {},
                                        "errors": "No answer from testhostname"}}
        result = _check_node(["test_hostname"], False, True)
        self.assertFalse(result)

        test_patch.return_value = {"test_hostname": {"data": {"status": "disabled"}, "errors": ""}}
        result = _check_node(["test_hostname"], False, True)
        self.assertFalse(result)

        test_patch.return_value = {"test_hostname": {"data": {"status": "stopped"}, "errors": ""}}
        result = _check_node(["test_hostname"], False, True)
        self.assertFalse(result)

        #now check with loose criteria
        test_patch.return_value = {"test_hostname": {"data": {"status": "disabled"}, "errors": ""}}
        result = _check_node(["test_hostname"], True, True)
        self.assertTrue(result)

        test_patch.return_value = {"test_hostname": {"data": {"status": "stopped"}, "errors": ""}}
        result = _check_node(["test_hostname"], True, True)
        self.assertTrue(result)

        test_patch.return_value = {"test_hostname": {"data": {},
                                        "errors": "No answer from testhostname"}}
        result = _check_node(["test_hostname"], True, True)
        self.assertFalse(result)

        # test puppet_applying_catalog_valid_state flag
        test_patch.return_value = {
            "test_hostname": {
                "data": {
                    "status": "applying a catalog"
                },
                "errors": ""
            }
        }
        result = _check_node(["test_hostname"], False, True)
        self.assertTrue(result)

        test_patch.return_value = {
            "test_hostname": {
                "data": {
                    "status": "applying a catalog"
                },
                "errors": ""
            }
        }
        result = _check_node(["test_hostname"], True, True)
        self.assertTrue(result)

        test_patch.return_value = {
            "test_hostname": {
                "data": {
                    "status": "applying a catalog"
                },
                "errors": ""
            }
        }
        result = _check_node(["test_hostname"], False, False)
        self.assertFalse(result)

        test_patch.return_value = {
            "test_hostname": {
                "data": {
                    "status": "applying a catalog"
                },
                "errors": ""
            }
        }
        result = _check_node(["test_hostname"], True, False)
        self.assertFalse(result)

    @patch('litp.core.node_utils.run_rpc_command')
    def test__check_node_down(self, test_patch):

        test_patch.return_value = {"test_hostname": {"data": {"pong": "12342"},
                                                     "errors": ""}}
        result = _check_node_down(["test_hostname"])
        self.assertFalse(result)

        test_patch.return_value = {"test_hostname": {"data": {"pong": "test"},
                                                     "errors": ""}}
        result = _check_node_down(["test_hostname"])
        self.assertFalse(result)

        test_patch.return_value = {"test_hostname": {"data": {},
                                        "errors": "No answer from testhostname"}}
        result = _check_node_down(["test_hostname"])
        self.assertTrue(result)

    @patch('litp.core.node_utils._check_node_down')
    def test_wait_for_node_down(self, _check_node_down_patch):
        mock_api = MagicMock()
        #litp.core.node_utils._check_node_down = MagicMock()
        wait_for_node_down(mock_api, "test_hostname", False)
        self.assertTrue(True)

    @patch('litp.core.node_utils._check_node')
    def test_wait_for_node(self, _check_node_patch):
        mock_api = MagicMock()
        #litp.core.node_utils._check_node = MagicMock()
        wait_for_node(mock_api, "test_hostname", False)
        # puppet_applying_catalog_valid_state parameter should be passed with
        #   False value
        _check_node_patch.assert_called_with("test_hostname", False, False)
        self.assertTrue(True)

    @patch('litp.core.node_utils._check_node')
    def test_wait_for_node_puppet_applying_catalog_valid(self,
                                                         _check_node_patch):
        mock_api = MagicMock()
        wait_for_node_puppet_applying_catalog_valid(mock_api, "test_hostname",
                                                    False)
        # puppet_applying_catalog_valid_state parameter should be passed with
        #   True value
        _check_node_patch.assert_called_with("test_hostname", False, True)
        self.assertTrue(True)

if __name__ == "__main__":

    unittest.main()
