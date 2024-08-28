from unittest import TestCase
from litp.core import rpc_commands
from mock import Mock, MagicMock, patch, call
from litp.core.exceptions import RpcExecutionException
from litp.core.rpc_commands import PuppetMcoProcessor
import os.path


two_failures = '[{"agent":"snapshot","data":{"status":5,"err":"  Volume ' \
               'group \\"vg_ms1\\" not found","out":""},"sender":"node1","statuscode":0,' \
               '"action":"create","statusmsg":"OK"},{"agent":"snapshot","data":{"status":' \
               '5,"err":"  Logical volume \\"trolo\\" already exists in volume group' \
               ' \\"vg_ms1\\"","out":""},"sender":"ms1","statuscode":0,"action":"create",' \
               '"statusmsg":"OK"}]\n'

one_failure = '[{"agent":"snapshot","data":{"status":' \
              '5,"err":"  Logical volume \\"trolo\\" already exists in volume group' \
              ' \\"vg_ms1\\"","out":""},"sender":"ms1","statuscode":0,"action":"create",' \
              '"statusmsg":"OK"}]\n'

one_timeout_one_ok = '''[
  {
    "agent": "snapshot",
    "data": {
      "status": "no output",
      "path": ""
    },
    "sender": "node1",
    "statuscode": 5,
    "action": "create",
    "statusmsg": "execution expired"
  },
  {
    "agent": "snapshot",
    "data": {
      "status": 0,
      "err": "",
      "path": "/trololo",
      "out": ""
    },
    "sender": "ms1",
    "statuscode": 0,
    "action": "create",
    "statusmsg": "OK"
  }
]
'''

no_json = "The rpc application failed to run, use -v for full error backtrace " \
          "details: Can't find DDL for agent plugin 'uhoh'"

sample_refresh_node_stats = {'n1':
                                 {'status': 'idling',
                                  'idling': True,
                                  'applying': False,
                                  'since_lastrun': 16,
                                  'daemon_present': True,
                                  'lastrun': 1430874155,
                                  'enabled': True,
                                  'disable_message': ''},
                             'n2': {'status': 'applying a catalog',
                                    'idling': False,
                                    'applying': True,
                                    'since_lastrun': 17,
                                    'daemon_present': True,
                                    'lastrun': 1430874163,
                                    'enabled': True,
                                    'disable_message': ''},
                             'ms1': {'status': 'idling',
                                     'idling': True,
                                     'applying': False,
                                     'since_lastrun': 8,
                                     'daemon_present': True,
                                     'lastrun': 1430874155,
                                     'enabled': True,
                                     'disable_message': ''}
                             }

sample_refresh_node_stats2 = {'n1':
                                  {'status': 'applying a catalog',
                                   'idling': False,
                                   'applying': True,
                                   'since_lastrun': 16,
                                   'daemon_present': True,
                                   'lastrun': 1430884155,
                                   'enabled': True,
                                   'disable_message': ''},
                              'n2': {'status': 'applying a catalog',
                                     'idling': False,
                                     'applying': True,
                                     'since_lastrun': 17,
                                     'daemon_present': True,
                                     'lastrun': 1430884163,
                                     'enabled': True,
                                     'disable_message': ''},
                              'ms1': {'status': 'applying a catalog',
                                      'idling': False,
                                      'applying': True,
                                      'since_lastrun': 8,
                                      'daemon_present': True,
                                      'lastrun': 1430884156,
                                      'enabled': True,
                                      'disable_message': ''}
                              }

sample_refresh_node_stats3 = {'n1':
                                  {'status': 'idling',
                                   'idling': True,
                                   'applying': False,
                                   'since_lastrun': 16,
                                   'daemon_present': True,
                                   'lastrun': 1430884155,
                                   'enabled': True,
                                   'disable_message': ''},
                              'n2': {'status': 'idling',
                                     'idling': True,
                                     'applying': False,
                                     'since_lastrun': 17,
                                     'daemon_present': True,
                                     'lastrun': 1430894163,
                                     'enabled': True,
                                     'disable_message': ''},
                              'ms1': {'status': 'idling',
                                      'idling': True,
                                      'applying': False,
                                      'since_lastrun': 8,
                                      'daemon_present': True,
                                      'lastrun': 1430884156,
                                      'enabled': True,
                                      'disable_message': ''}
                              }

sample_refresh_node_stats_almost_disabled = {
    'n1':
          {'status': 'applying a catalog',
           'idling': False,
           'applying': True,
           'since_lastrun': 16,
           'daemon_present': True,
           'lastrun': 1430884155,
           'enabled': False,
           'disable_message': ''},
    'n2':
          {'status': 'applying a catalog',
         'idling': False,
         'applying': True,
         'since_lastrun': 17,
         'daemon_present': True,
         'lastrun': 1430884163,
         'enabled': False,
         'disable_message': ''},
    'ms1':
          {'status': 'applying a catalog',
          'idling': False,
          'applying': True,
          'since_lastrun': 8,
          'daemon_present': True,
          'lastrun': 1430884156,
          'enabled': False,
          'disable_message': ''}
}

sample_refresh_node_stats_disabled = {
    'n1':
      {"status": "disabled",
      "daemon_present": True,
      "disable_message": "Disabled via MCollective by uid=0 at 2015-08-05 12:25",
      "lastrun": 1438773947,
      "since_lastrun": 7962,
      "enabled": False,
      "applying": False,
      "idling": True
       },
    'n2':
      {"status": "disabled",
      "daemon_present": True,
      "disable_message": "Disabled via MCollective by uid=0 at 2015-08-05 12:25",
      "lastrun": 1438773960,
      "since_lastrun": 7949,
      "enabled": False,
      "applying": False,
      "idling": True
       }
}

sample_refresh_node_stats_disabled2 = {
    'n1':
      {"status": "disabled",
      "daemon_present": True,
      "disable_message": "Disabled via MCollective by uid=0 at 2015-08-05 12:25",
      "lastrun": 1438774047,
      "since_lastrun": 20,
      "enabled": False,
      "applying": False,
      "idling": True
       },
    'n2':
      {"status": "disabled",
      "daemon_present": True,
      "disable_message": "Disabled via MCollective by uid=0 at 2015-08-05 12:25",
      "lastrun": 1438773960,
      "since_lastrun": 7949,
      "enabled": False,
      "applying": False,
      "idling": True
       }
}

sample_config_version_stats1 = {
    'ms1':
      {"since_lastrun": 21,
      "changed_resources": 0,
      "config_retrieval_time": 4.86780381202698,
      "managed": False,
      "out_of_sync_resources": 0,
      "config_version": "0",
      "lastrun": 1455094289,
      "total_resources": 265,
      "failed_resources": 0,
      "total_time": 9.46532181202698
       },
    'n1':
      {"since_lastrun": 219,
      "changed_resources": 0,
      "config_retrieval_time": 1.92987513542175,
      "managed": False,
      "out_of_sync_resources": 0,
      "config_version": "0",
      "lastrun": 1455094092,
      "total_resources": 211,
      "failed_resources": 0,
      "total_time": 6.04967513542175
      },
    'n2':
      {"since_lastrun": 21,
      "changed_resources": 0,
      "config_retrieval_time": 4.86780381202698,
      "managed": False,
      "out_of_sync_resources": 0,
      "config_version": "0",
      "lastrun": 1455094289,
      "total_resources": 265,
      "failed_resources": 0,
      "total_time": 9.46532181202698
      },
}

# ms1 has applied the catalog we're looking for, n1 still stuck
sample_config_version_stats2 = {
    'ms1':
       {"since_lastrun": 16,
      "changed_resources": 0,
      "config_retrieval_time": 3.7974259853363,
      "managed": False,
      "out_of_sync_resources": 0,
      "config_version": "1",
      "lastrun": 1455094840,
      "total_resources": 265,
      "failed_resources": 0,
      "total_time": 8.0416749853363
       },
    'n1':
        {"since_lastrun": 106,
      "changed_resources": 0,
      "config_retrieval_time": 0.859220027923584,
      "managed": False,
      "out_of_sync_resources": 0,
      "config_version": "0",
      "lastrun": 1455094751,
      "total_resources": 211,
      "failed_resources": 0,
      "total_time": 4.98861102792358
       },
    'n2':
        {"since_lastrun": 106,
      "changed_resources": 0,
      "config_retrieval_time": 0.859220027923584,
      "managed": False,
      "out_of_sync_resources": 0,
      "config_version": "0",
      "lastrun": 1455094751,
      "total_resources": 211,
      "failed_resources": 0,
      "total_time": 4.98861102792358
      }
}

# n1 finally applies the catalog
sample_config_version_stats3 = {
    'ms1':
        {"since_lastrun": 167,
      "changed_resources": 0,
      "config_retrieval_time": 3.24784898757935,
      "managed": False,
      "out_of_sync_resources": 0,
      "config_version": "1",
      "lastrun": 1455095379,
      "total_resources": 265,
      "failed_resources": 0,
      "total_time": 7.58803598757935
       },
    'n1':
        {"since_lastrun": 12,
      "changed_resources": 0,
      "config_retrieval_time": 3.71541595458984,
      "managed": False,
      "out_of_sync_resources": 0,
      "config_version": "1",
      "lastrun": 1455095534,
      "total_resources": 211,
      "failed_resources": 0,
      "total_time": 7.93244995458984
     },
    'n2':
        {"since_lastrun": 106,
         "changed_resources": 0,
         "config_retrieval_time": 0.859220027923584,
         "managed": False,
         "out_of_sync_resources": 0,
         "config_version": "0",
         "lastrun": 1455094751,
         "total_resources": 211,
         "failed_resources": 0,
         "total_time": 4.98861102792358
         },
}
sample_config_version_stats4 = {
    'ms1':
     {"since_lastrun": 167,
      "changed_resources": 0,
      "config_retrieval_time": 3.24784898757935,
      "managed": False,
      "out_of_sync_resources": 0,
      "config_version": "1",
      "lastrun": 1455095379,
      "total_resources": 265,
      "failed_resources": 0,
      "total_time": 7.58803598757935
       },
    'n1':
        {"since_lastrun": 12,
      "changed_resources": 0,
      "config_retrieval_time": 3.71541595458984,
      "managed": False,
      "out_of_sync_resources": 0,
      "config_version": "1",
      "lastrun": 1455095534,
      "total_resources": 211,
      "failed_resources": 0,
      "total_time": 7.93244995458984
     },
    'n2':
     {"since_lastrun": 106,
      "changed_resources": 0,
      "config_retrieval_time": 0.859220027923584,
      "managed": False,
      "out_of_sync_resources": 0,
      "config_version": "1",
      "lastrun": 1455094751,
      "total_resources": 211,
      "failed_resources": 0,
      "total_time": 4.98861102792358
      },
}

def give_results(results):
    for result in results:
        yield result


class TestCertCleanup(TestCase):
    @patch('litp.core.rpc_commands.PuppetMcoProcessor._get_resolv_domains',
            return_value=['example.com'])
    def test_get_ms_names(self, o):
        names = rpc_commands.PuppetMcoProcessor()._get_ms_names('MS1')
        self.assertTrue('ms1' in names)
        self.assertTrue('ms1.example.com' in names)

    @patch('litp.core.rpc_commands.PuppetMcoProcessor._get_ms_names',
            return_value=['ms1'])
    @patch('litp.core.rpc_commands.PuppetMcoProcessor._stop_puppet_check',
            return_value=(True, True))
    @patch('litp.core.rpc_commands.PuppetMcoProcessor._start_puppet_check',
            return_value=(True, True))
    @patch('litp.core.rpc_commands.PuppetMcoProcessor._get_puppet_certs',
            return_value=('MS1:node1:node2', None))
    def test_clean_puppet_certs(self, *a):
        mock_run_puppet = MagicMock(return_value=None)
        with patch('litp.core.rpc_commands.PuppetMcoProcessor.run_puppet', mock_run_puppet):
            the_ms = Mock()
            the_ms.hostname = 'MS1'
            node1 = Mock()
            node1.hostname = 'node1'
            node2 = Mock()
            node2.hostname = 'node2'
            rpc_commands.PuppetMcoProcessor().clean_puppet_certs([the_ms, node1, node2], the_ms.hostname)
            mock_run_puppet.assert_any_call([the_ms.hostname], "puppetcerts", "clean_cert", {"node": node1.hostname})
            mock_run_puppet.assert_any_call([the_ms.hostname], "puppetcerts", "clean_cert", {"node": node2.hostname})
            self.assertEquals(len(mock_run_puppet.call_args_list), 2)

    @patch('litp.core.rpc_commands.PuppetMcoProcessor._get_ms_names',
            return_value=['ms1'])
    @patch('litp.core.rpc_commands.PuppetMcoProcessor._stop_puppet_check',
            return_value=(False, True))
    @patch('litp.core.rpc_commands.PuppetMcoProcessor._start_puppet_check',
            return_value=(True, True))
    @patch('litp.core.rpc_commands.PuppetMcoProcessor._get_puppet_certs',
            return_value=('MS1:node1:node2', None))
    def test_clean_puppet_certs_stopped(self, *a):
        mock_run_puppet = MagicMock(return_value=None)
        with patch('litp.core.rpc_commands.PuppetMcoProcessor.run_puppet', mock_run_puppet):
            the_ms = Mock()
            the_ms.hostname = 'MS1'
            node1 = Mock()
            node1.hostname = 'node1'
            node2 = Mock()
            node2.hostname = 'node2'
            rpc_commands.PuppetMcoProcessor().clean_puppet_certs([the_ms, node1, node2], the_ms.hostname)
            mock_run_puppet.assert_any_call([the_ms.hostname], "puppetcerts", "clean_cert", {"node": node1.hostname})
            mock_run_puppet.assert_any_call([the_ms.hostname], "puppetcerts", "clean_cert", {"node": node2.hostname})
            self.assertEquals(a[1].call_count, 0) # _start_puppet_check
            self.assertEquals(a[2].call_count, 1) # _stop_puppet_check
            self.assertEquals(len(mock_run_puppet.call_args_list), 2)



class TestRpcCommands(TestCase):
    def setUp(self):
        self.p = rpc_commands.PuppetExecutionProcessor()
        self.p._wait = MagicMock()
        self.pc = rpc_commands.PuppetCatalogRunProcessor()
        self.pc._wait = MagicMock()
        self.pc._find_all_nodes_orig = self.pc._find_all_nodes
        self.pc._find_all_nodes = MagicMock(return_value=['ms1', 'n1', 'n2'])

    @patch('litp.core.nextgen.puppet_manager.PuppetManager.write_new_config_version')
    def test_update_config_problem(self, mock_write_new_conf):
        # TORF-158758: Be aware, ENMinst directly calls the
        # PuppetCatalogRunProcessor.update_config_version()
        mock_write_new_conf.return_value = 0
        actual = self.pc.update_config_version()
        self.assertEqual(1, mock_write_new_conf.call_count)
        self.assertEqual(0, actual)

    def test_validate_input_with_timestamp(self):
        # TORF-158758: mco response with legacy timestamp
        data = {
            'ms1':
              {"since_lastrun": 21,
              "changed_resources": 0,
              "config_retrieval_time": 4.86780381202698,
              "managed": False,
              "out_of_sync_resources": 0,
              "config_version": "2016-01-19 09:51:08.252714",
              "lastrun": 1455094289,
              "total_resources": 265,
              "failed_resources": 0,
              "total_time": 9.46532181202698
           }
        }
        # config_version is converted to int
        expected = {
            'ms1':
              {"since_lastrun": 21,
              "changed_resources": 0,
              "config_retrieval_time": 4.86780381202698,
              "managed": False,
              "out_of_sync_resources": 0,
              "config_version": 0,
              "lastrun": 1455094289,
              "total_resources": 265,
              "failed_resources": 0,
              "total_time": 9.46532181202698
           }
        }
        self.pc._validate_input(data)
        self.assertEqual(expected, data)

    def test_is_litp_killed(self):
        mco_processor = PuppetMcoProcessor(Mock())
        with patch('litp.core.rpc_commands.cherrypy') as mock_cherry:
            mock_cherry.config = {}
            self.assertFalse(mco_processor._is_litp_killed())
            mock_puppet = Mock(killed=True)
            mock_cherry.config = {'puppet_manager': mock_puppet}
            self.assertTrue(mco_processor._is_litp_killed())
            mock_puppet.killed = False
            self.assertFalse(mco_processor._is_litp_killed())

    def test_create_args_stop_start(self):
        stop_cmd = ['mco', 'rpc', '--json', '--timeout=60', '-I', 'ms1',
                    '-I', 'node1', '-I', 'node2', 'service', 'stop',
                    'service=puppet']
        start_cmd = ['mco', 'rpc', '--json', '--timeout=60', '-I', 'ms1',
                     '-I', 'node1', '-I', 'node2', 'service', 'start',
                     'service=puppet']
        self.assertEqual(stop_cmd, rpc_commands._create_rpc_args(
            ['ms1', 'node1', 'node2'], "service", "stop",
            {"service": "puppet"}, 60))
        self.assertEqual(start_cmd, rpc_commands._create_rpc_args(
            ['ms1', 'node1', 'node2'], "service", "start",
            {"service": "puppet"}, 60))

    def test_run_rpc_command(self):
        mock_obj = MagicMock(return_value=(two_failures, ""))
        with patch('litp.core.rpc_commands._run_process', mock_obj):
            result = rpc_commands.run_rpc_command(['ms1', 'node1'],
                                                  'snapshot',
                                                  'create',
                                                  {
                                                      'path': '/dev/vg_ms1/lv_home',
                                                      'size': '1G',
                                                      'name': 'trololo'}
                                                  )
            self.assertEquals({'status': 5,
                               'err': '  Logical volume "trolo" already exists in volume group "vg_ms1"',
                               'out': ''}, result['ms1']['data'])
            self.assertEquals({"status": 5,
                               "err": "  Volume group \"vg_ms1\" not found",
                               "out": ""}, result['node1']['data'])
        # try with 1 node in the result now
        mock_obj = MagicMock(return_value=(one_failure, ""))
        with patch('litp.core.rpc_commands._run_process', mock_obj):
            result = rpc_commands.run_rpc_command(['ms1'],
                                                  'snapshot',
                                                  'create',
                                                  {
                                                      'path': '/dev/vg_ms1/lv_home',
                                                      'size': '1G',
                                                      'name': 'trololo'}
                                                  )
            self.assertEquals({'status': 5,
                               'err': '  Logical volume "trolo" already exists in volume group "vg_ms1"',
                               'out': ''}, result['ms1']['data'])

    def test_run_rpc_no_json_response(self):
        mock_obj = MagicMock(return_value=("", no_json))
        with patch('litp.core.rpc_commands._run_process', mock_obj):
            self.assertEquals({'node1':
                                   {'errors':
                                        "node1: The rpc application failed to run, use -v for full error backtrace details: Can't find DDL for agent plugin 'uhoh'",
                                    'data': {}
                                    },
                               'ms1':
                                   {'errors':
                                        "ms1: The rpc application failed to run, use -v for full error backtrace details: Can't find DDL for agent plugin 'uhoh'",
                                    'data': {}
                                    }
                               },
                              rpc_commands.run_rpc_command(['ms1', 'node1'],
                                                           'uhoh',
                                                           'create',
                                                           {
                                                               'path': '/dev/vg_ms1/lv_home',
                                                               'size': '1G',
                                                               'name': 'trololo'}
                                                           ))

    def test_rpc_cmd_is_right(self):
        mock_obj = MagicMock(return_value=('[]', ""))
        with patch('litp.core.rpc_commands._run_process', mock_obj):
            rpc_commands.run_rpc_command(['ms', 'pn'], 'snapshot', 'create',
                                         {'path': '/dev/vg_ms1/lv_home',
                                          'size': '1G',
                                          'name': 'trololo'})
            args = ['mco', 'rpc', '--json', '--timeout=60', '-I', 'ms', '-I',
                    'pn',
                    'snapshot', 'create',
                    'path=/dev/vg_ms1/lv_home',
                    'name=trololo',
                    'size=1G']
            rpc_commands._run_process.assert_called_once_with(args)
            rpc_commands.run_rpc_command([], 'snapshot', 'create', {},
                timeout=3)
            args = ['mco', 'rpc', '--json', '--timeout=3', 'snapshot',
                    'create']
            rpc_commands._run_process.assert_called_with(args)

    def test_missing_response_from_node(self):
        mock_obj = MagicMock(return_value=(one_failure, ""))
        with patch('litp.core.rpc_commands._run_process', mock_obj):
            result = rpc_commands.run_rpc_command(['ms1', 'missing_node'],
                                                  'snapshot', 'create',
                                                  {
                                                      'path': '/dev/vg_ms1/lv_home',
                                                      'size': '1G',
                                                      'name': 'trololo'})
            self.assertEquals('No answer from node missing_node',
                              result['missing_node']['errors'])

    def test_timeouts_get_filled(self):
        # mcollective will return empty values if a node times out
        mock_obj = MagicMock(return_value=(one_timeout_one_ok, ""))
        with patch('litp.core.rpc_commands._run_process', mock_obj):
            result = rpc_commands.run_rpc_command(['ms1', 'node1'],
                                                  'snapshot', 'create',
                                                  {'path': '/trololo',
                                                   'size': '1G',
                                                   'name': 'trololo'})
            self.assertEquals('node1: execution expired',
                              result['node1']['errors'])

    def test_base_returns_no_output(self):
        c = rpc_commands.RpcCommandProcessorBase()
        mock_api = MagicMock()
        mock_api.rpc_command.return_value = {'n1': {}}
        c._get_output = MagicMock()
        c.execute_rpc_and_process_result(mock_api, ['n1'], 'agent', 'action',
                                         None, None)
        c._get_output.assert_has_calls([])

    def test_base_returns_output(self):
        c = rpc_commands.RpcCommandOutputProcessor()
        mock_api = MagicMock()
        mock_api.rpc_command.return_value = {'n1': {}}
        c._get_output = MagicMock()
        c.execute_rpc_and_process_result(mock_api, ['n1'], 'agent', 'action',
                                         None, None)
        c._get_output.assert_has_calls(call('n1', {}))

    def test_rpcexception_raised(self):
        c = rpc_commands.RpcCommandProcessorBase()
        mock_api = MagicMock()
        mock_api.rpc_command = MagicMock(side_effect=Exception("nooooo"))
        self.assertRaises(RpcExecutionException,
                          c.execute_rpc_and_process_result,
                          mock_api, [], 'agent', 'action', None, None)

    def test_mco_errors_returned(self):
        c = rpc_commands.RpcCommandProcessorBase()
        mock_api = MagicMock()
        mock_api.rpc_command.return_value = {
            'n1': {'errors': 'oops', 'data': {}}}
        self.assertEqual(({}, {'n1': ['oops']}),
            c.execute_rpc_and_process_result(mock_api,
                                             ['n1'],
                                             'agent',
                                             'action',
                                             None,
                                             None))

    def test_agent_errors_returned(self):
        c = rpc_commands.RpcCommandProcessorBase()
        mock_api = MagicMock()
        mock_api.rpc_command.return_value = {'n1': {'errors': '',
                                                    'data': {'status': 1,
                                                             'out': 'blah',
                                                             'err': 'errors'}}}
        self.assertEqual(({}, {'n1': ['n1 failed with message: errors']}),
            c.execute_rpc_and_process_result(mock_api,
                                             ['n1'],
                                             'agent',
                                             'action',
                                             None,
                                             None))

    def test_retval_with_output(self):
        c = rpc_commands.RpcCommandOutputProcessor()
        mock_api = MagicMock()
        mock_api.rpc_command.return_value = {'n1': {'errors': '',
                                                    'data': {'status': 1,
                                                             'out': 'blah',
                                                             'err': 'errors'}}}
        self.assertEqual(
            ({'n1': 'blah'}, {'n1': ['n1 failed with message: errors']}),
            c.execute_rpc_and_process_result(mock_api,
                                             ['n1'],
                                             'agent',
                                             'action',
                                             None,
                                             None))

    def test_retries(self):
        mock_obj = MagicMock(return_value=('[]', ""))
        with patch('litp.core.rpc_commands._run_process', mock_obj):
            self.assertEqual(
                {'n1': {'errors': 'No answer from node n1', 'data': {}},
                 'n2': {'errors': 'No answer from node n2', 'data': {}}},
                rpc_commands.run_rpc_command(['n1', 'n2'],
                                             'agent',
                                             'action',
                                             retries=2))
            self.assertEqual(3, mock_obj.call_count)

    def test_base_retries(self):
        c = rpc_commands.RpcCommandProcessorBase()
        c._get_output = MagicMock()
        mock_obj = MagicMock(return_value=('[]', ""))
        with patch('litp.core.rpc_commands._run_process', mock_obj):
            mock_api = MagicMock()
            mock_api.rpc_command.return_value = rpc_commands.run_rpc_command(
                ['n1'], 'agent', 'action',
                action_kwargs=None, timeout=None, retries=2)
            c.execute_rpc_and_process_result(mock_api, ['n1'], 'agent',
                                             'action', None, 2)
            self.assertEqual(3, mock_obj.call_count)

    @patch('litp.core.rpc_commands.time.time', side_effect=[100, 100, 500])
    def test_init_stops_on_timeout(self, _):
        self.p._init_data = MagicMock(side_effect=rpc_commands.McoRunError())
        self.assertRaises(rpc_commands.McoRunError,
                          self.p.trigger_and_wait, ['ms1'])

    @patch('litp.core.rpc_commands.time.time', return_value=69.96)
    def test_init_called_once_on_success(self, _):
        self.p._init_data = MagicMock()
        self.p._get_nodes_by_state = MagicMock(return_value=[[], [], [], []])
        self.p.trigger_and_wait(['ms1'])
        self.assertEqual(1, len(self.p._init_data.call_args_list))

    def test_init_data(self):
        self.p._refresh_node_stats = MagicMock(
            return_value=sample_refresh_node_stats)
        self.assertEqual({}, self.p.nodes)
        self.p._init_data(['ms1', 'n1', 'n2'])
        self.assertEqual({
            'n1': {'lastrun': 1430874155, 'state': 'nontriggered'},
            'n2': {'lastrun': 1430874163, 'state': 'prevrun'},
            'ms1': {'lastrun': 1430874155, 'state': 'nontriggered'}
        },
            self.p.nodes)

    def test_update_refreshed_nodes(self):
        self.p.nodes = {'ms1': {'state': 'prevrun', 'lastrun': 1430874155},
                        'n1': {'state': 'prevrun', 'lastrun': 1430874155},
                        'n2': {'state': 'prevrun', 'lastrun': 1430874155}}
        self.p._update_refreshed_nodes(sample_refresh_node_stats)
        self.assertEqual({'n1': {'lastrun': 1430874155, 'state': 'prevrun'},
                          'n2': {'lastrun': 1430874163,
                                 'state': 'nontriggered'},
                          'ms1': {'lastrun': 1430874155, 'state': 'prevrun'}},
                         self.p.nodes)
        self.p._update_refreshed_nodes(sample_refresh_node_stats2)
        self.assertEqual(
            {'n1': {'lastrun': 1430884155, 'state': 'nontriggered'},
             'n2': {'lastrun': 1430884163, 'state': 'completed'},
             'ms1': {'lastrun': 1430884156, 'state': 'nontriggered'}},
            self.p.nodes)

    def test_get_nodes_by_state(self):
        self.p.nodes = {
            'ms1': {'state': 'prevrun', 'lastrun': 1430874155},
            'n1': {'state': 'nontriggered', 'lastrun': 1430874155},
            'n2': {'state': 'triggered', 'lastrun': 1430874155},
            'n3': {'state': 'completed', 'lastrun': 1430874155},
            'n4': {'state': 'lolwut', 'lastrun': 1430874155}
        }
        self.assertEqual((['ms1'], ['n1'], ['n2'], ['n3']),
                         self.p._get_nodes_by_state())

    def test_trigger_and_wait(self):
        self.p._trigger_puppet = MagicMock(side_effect=[['n1', 'ms1'], ['n2']])
        self.p._refresh_node_stats = MagicMock(
            side_effect=[sample_refresh_node_stats,
                         sample_refresh_node_stats2,
                         sample_refresh_node_stats3]
        )
        self.p.trigger_and_wait(['ms1', 'n1', 'n2'])
        self.assertEqual({'n1': {'lastrun': 1430884155, 'state': 'completed'},
                          'n2': {'lastrun': 1430894163, 'state': 'completed'},
                          'ms1': {'lastrun': 1430884156, 'state': 'completed'}
                          },
                         self.p.nodes)

    def test_wait(self):
        # n1 has an ongoing run, n2 is idling
        self.p._refresh_node_stats_lockfile = MagicMock(
            return_value={'n1': True, 'n2': False}
        )
        # n1 finishes the run in the second call
        self.p._refresh_node_stats = MagicMock(
            side_effect=[sample_refresh_node_stats_disabled,
                         sample_refresh_node_stats_disabled2]
        )
        self.p.wait(['n1', 'n2'])
        self.assertEqual({'n1': {'lastrun': 1438774047, 'state': 'nontriggered'},
                          'n2': {'lastrun': 1438773960, 'state': 'nontriggered'}
                          },
                         self.p.nodes)

    def test_puppet_enabled_raises_error(self):
        self.p._refresh_node_stats = MagicMock(
            return_value=sample_refresh_node_stats2
        )
        self.assertRaises(RpcExecutionException,
                          self.p.wait, ['n1', 'n2', 'ms1'])

    def test_wait_lockfile_overrides_mcoagent(self):
        # n1 has an ongoing run, n2 is idling
        self.p._refresh_node_stats_lockfile = MagicMock(
            return_value={'ms1': False, 'n1': False, 'n2': False}
        )
        # n1 finishes the run in the second call
        self.p._refresh_node_stats = MagicMock(
            return_value=sample_refresh_node_stats_almost_disabled
        )
        self.p.wait(['n1', 'n2', 'ms1'])
        self.assertEqual({'n1': {'lastrun': 1430884155, 'state': 'nontriggered'},
                          'n2': {'lastrun': 1430884163, 'state': 'nontriggered'},
                          'ms1': {'lastrun': 1430884156, 'state': 'nontriggered'}},
                         self.p.nodes)

    def test_is_puppet_already_applying(self):
        applying_result = {
                'errors': 'ms1: Puppet is currently applying a catalog, cannot run now',
                'data': {'initiated_at': 0, 'summary': 'Puppet is currently applying a catalog, cannot run now'}
                }
        self.assertTrue(rpc_commands.is_puppet_already_applying(applying_result))
        status_result = {
                'errors': '',
                'data': {
                    'status': 'applying a catalog', 'lastrun': 1447737382,
                    'applying': True, 'since_lastrun': 177, 'daemon_present': True,
                    'idling': False, 'enabled': True,
                    'message': 'Currently applying a catalog; last completed run 2 minutes 57 seconds ago',
                    'disable_message': ''
                    }
                }
        self.assertFalse(rpc_commands.is_puppet_already_applying(status_result))

    def test_has_errors_with_is_puppet_already_applying(self):
        applying_result = {
                'ms1': {
                    'errors': 'ms1: Puppet is currently applying a catalog, cannot run now',
                    'data': {
                        'initiated_at': 0,
                        'summary': 'Puppet is currently applying a catalog, cannot run now'
                        }
                    },
                'node1': {
                    'errors': 'node1: Puppet is currently applying a catalog, cannot run now',
                    'data': {
                        'initiated_at': 0,
                        'summary': 'Puppet is currently applying a catalog, cannot run now'
                        }
                    }
                }
        self.assertFalse(rpc_commands.has_errors(applying_result))
        error_result = {
                'ms1': {
                    'errors': 'ms1: Puppet is currently applying a catalog, cannot run now',
                    'data': {
                        'initiated_at': 0,
                        'summary': 'Puppet is currently applying a catalog, cannot run now'
                        }
                    },
                'node1': {
                    'errors': 'cannot reach node1',
                    'data': {
                        'initiated_at': 0,
                        'summary': 'cannot reach node1',
                        }
                    }
                }
        self.assertTrue(rpc_commands.has_errors(error_result))

    @patch('litp.core.rpc_commands.clean_puppet_cache', MagicMock())
    def test_trigger_and_wait_cached(self):
        self.pc._trigger_puppet = MagicMock(return_value=set(['n1', 'ms1']))
        self.pc._refresh_node_stats = MagicMock(
            side_effect=[sample_config_version_stats1,
                         sample_config_version_stats1,
                         sample_config_version_stats2,
                         sample_config_version_stats3]
        )
        version = 1
        self.pc._is_plan_running = MagicMock(return_value=False)
        self.pc._touch_manifest_dir = MagicMock(return_value=True)
        self.pc._get_applying_nodes = MagicMock(return_value=set(['ms1', 'n1']))
        self.pc._disable_puppet(['ms1', 'n1'])
        self.pc.trigger_and_wait(version, ['ms1', 'n1'])
        self.assertEqual([], self.pc.nodes)

    @patch('litp.core.rpc_commands.clean_puppet_cache', MagicMock())
    def test_timeout_exception(self):
        self.pc._get_applying_nodes = MagicMock(return_value=set(['n1', 'ms1']))
        self.pc._get_failed_nodes = MagicMock(return_value=set())
        self.pc._trigger_puppet = MagicMock(return_value=set(['n1', 'ms1']))
        self.pc._refresh_node_stats = MagicMock(
            side_effect=[sample_config_version_stats1] * 3006
        )
        version = 1
        self.pc._touch_manifest_dir = MagicMock(return_value=True)
        self.pc._is_plan_running = MagicMock(return_value=False)
        self.assertRaises(RpcExecutionException,
                          self.pc.trigger_and_wait, version,
                          ['ms1', 'n1']
        )

    @patch('litp.core.rpc_commands.clean_puppet_cache', MagicMock())
    def test_timeout_exception_when_always_applying(self):
        self.pc._get_applying_nodes = MagicMock(return_value=set(['n1', 'ms1']))
        self.pc._refresh_node_stats = MagicMock(
            side_effect=[sample_config_version_stats1] * 3006
        )
        self.pc._trigger_puppet = MagicMock()
        version = 1
        self.pc._touch_manifest_dir = MagicMock(return_value=True)
        self.pc._is_plan_running = MagicMock(return_value=False)
        self.assertRaises(RpcExecutionException,
                          self.pc.trigger_and_wait, version,
                          ['ms1', 'n1'])
        self.assertFalse(self.pc._trigger_puppet.called)

    @patch('litp.core.rpc_commands.clean_puppet_cache', MagicMock())
    def test_trigger_and_wait_several_triggers(self):
        self.pc._trigger_puppet = MagicMock(side_effect=[set(['ms1']),
                                                         set([]),
                                                         set(['n1'])])

        self.pc._refresh_node_stats = MagicMock(
            side_effect=[sample_config_version_stats1,
                         sample_config_version_stats1,
                         sample_config_version_stats2,
                         sample_config_version_stats3]
        )
        version = 1
        self.pc._is_plan_running = MagicMock(return_value=False)
        self.pc._touch_manifest_dir = MagicMock(return_value=True)
        self.pc._get_failed_nodes = MagicMock(return_value=set())
        self.pc._enable_puppet = MagicMock(side_effect=[set(['ms1', 'n1', 'n2']),
                                                        set(['ms1', 'n1']),
                                                        set(['ms1', 'n1', 'n2']),
                                                        set(['ms1', 'n1', 'n2'])])
        self.pc._disable_puppet = MagicMock(side_effect=[set(['ms1', 'n1', 'n2']),
                                                         set(['ms1', 'n1']),
                                                         set(['n1']),
                                                         set(['n1'])])
        self.pc._get_applying_nodes = MagicMock(side_effect=[set(['ms1', 'n1']),
                                                             set(['ms1', 'n1']),
                                                             set(),
                                                             set(['ms1', 'n1']),
                                                             set(['ms1']),
                                                             set(['n1']),
                                                             set(['ms1']),
                                                             set(['n1']),
                                                             set(['n1']),
                                                             set([])])

        self.pc.trigger_and_wait(version, ['ms1', 'n1'])
        calls = [call(set(['n1', 'ms1']))]
        self.pc._trigger_puppet.assert_has_calls(calls)

    @patch('litp.core.rpc_commands.clean_puppet_cache', MagicMock())
    def test_trigger_and_wait_several_triggers2(self):
        # in this case there is only one call to _trigger_puppet with 'n1'.
        # this proves that the method only gets called if there is any node
        # left in which puppet needs to be triggered
        self.pc._trigger_puppet = MagicMock(side_effect=[set(['ms1']),
                                                         set(['n1'])])
        self.pc._refresh_node_stats = MagicMock(
            side_effect=[sample_config_version_stats1,
                         sample_config_version_stats1,
                         sample_config_version_stats2,
                         sample_config_version_stats3]
        )
        version = 1
        self.pc._is_plan_running = MagicMock(return_value=False)
        self.pc._touch_manifest_dir = MagicMock(return_value=True)
        self.pc._disable_puppet(['ms1', 'n1'])
        self.pc._get_failed_nodes = MagicMock(return_value=set())
        self.pc._get_applying_nodes = MagicMock(side_effect=[set([]),
                                                             set(['ms1']),
                                                             set(['ms1']),
                                                             set(['ms1']),
                                                             set(['ms1']),
                                                             set(['n1']),
                                                             set(['n1']),
                                                             set(['n1']),
                                                             set([])])
        self.pc.trigger_and_wait(version, ['ms1', 'n1'])
        calls = [call(set(['n1', 'ms1'])), call(set(['n1']))]
        self.pc._trigger_puppet.assert_has_calls(calls)

    @patch('litp.core.rpc_commands.clean_puppet_cache', MagicMock())
    @patch('litp.core.rpc_commands.PuppetCatalogRunProcessor.PUPPET_CONCURRENCY', 3)
    def test_trigger_and_wait_concurrency(self):
        # Verifies (via the no of calls to trigger puppet) that if concurrency <=
        # applying nodes trigger puppet wont be called
        # Verifies that if a node is completed without being triggered (via scheduled run
        # (ms1)) we won't trigger puppet on that node.

        def trigger_puppet(nodes_to_trigger):
            return nodes_to_trigger

        self.pc._trigger_puppet = MagicMock(side_effect=trigger_puppet)
        self.pc._refresh_node_stats = MagicMock(
            side_effect=[sample_config_version_stats1,
                         sample_config_version_stats2,
                         sample_config_version_stats2,
                         sample_config_version_stats3,
                         sample_config_version_stats4]
        )
        version = 1
        self.pc._touch_manifest_dir = MagicMock(return_value=True)
        self.pc._disable_puppet(['ms1', 'n1', 'n2'])
        self.pc._get_applying_nodes = MagicMock(side_effect=[set([]),
                                                             set(['ms1', 'n1', 'n2']),
                                                             set(['ms1', 'n1', 'n2']),
                                                             set(['n1', 'n2']),
                                                             set(['n1', 'n2']),
                                                             set(['n1', 'n2']),
                                                             set(['n2']),
                                                             set([]),
                                                             set([])])
        self.pc._is_plan_running = MagicMock(return_value=False)
        self.pc._get_failed_nodes = MagicMock(side_effect=[set([]),
                                                           set([]),
                                                           set([]),
                                                           set([]),
                                                           set([])])
        self.pc.trigger_and_wait(version, ['ms1', 'n1', 'n2'])

        calls = [call(set(['ms1', 'n1', 'n2']))]
        self.pc._trigger_puppet.assert_has_calls(calls)

    @patch('litp.core.rpc_commands._run_process',
           MagicMock(return_value=("", "")))
    def test_trigger_and_wait_raises_rpcexecutionexception(self):
        version = 1
        self.pc._touch_manifest_dir = MagicMock(return_value=True)
        self.pc._is_plan_running = MagicMock(return_value=False)
        self.pc._find_all_nodes = self.pc._find_all_nodes_orig
        self.assertRaises(RpcExecutionException,
                          self.pc.trigger_and_wait, version,
                          ['ms1', 'n1'])

    def test_trigger_and_wait_is_plan_running_raises_exception(self):
        version = 1
        self.pc._is_plan_running = MagicMock(return_value=True)
        self.assertRaises(RpcExecutionException, self.pc.trigger_and_wait, version,
                          ['ms1', 'n1', 'n2'])

    def test_for_failed_nodes(self):
        nodes = ['ms1', 'n1', 'n2', 'n3']
        untriggered_nodes = set([])
        applying_nodes = set(['ms1', 'n1'])
        self.pc._get_applying_nodes = MagicMock(return_value=set(['ms1', 'n1']))
        result = self.pc._get_failed_nodes(nodes, untriggered_nodes, applying_nodes)
        self.assertEqual(result, set(['n2', 'n3']))

    def test_trigger_puppet_with_concurrency(self):
        # concurrency < len(applying)
        # No calls to trigger puppet and empty set returned
        with patch('litp.core.rpc_commands.PuppetCatalogRunProcessor.'
                   'PUPPET_CONCURRENCY', 2):
            all_nodes = ['ms1', 'n1', 'n2']
            self.pc._trigger_puppet = MagicMock()
            self.pc._get_applying_nodes = \
                MagicMock(return_value=set(['ms1', 'n1', 'n2']))
            result = self.pc._trigger_puppet_with_concurrency(
                set(['ms1', 'n1', 'n2']), all_nodes)

            self.assertFalse(self.pc._trigger_puppet.called)
            self.assertEqual(set(), result)

        # concurrency > len(applying) and
        # len(untriggered - applying) = 0
        # all nodes in untriggered set applying.
        # No calls to trigger puppet and empty set returned
        with patch('litp.core.rpc_commands.PuppetCatalogRunProcessor.'
                   'PUPPET_CONCURRENCY', 4):
            self.pc._trigger_puppet = MagicMock()
            self.pc._get_applying_nodes = \
                MagicMock(side_effect=[set(['ms1', 'n1', 'n2']),
                                       set(['ms1', 'n1', 'n2'])])
            self.pc._trigger_puppet_with_concurrency(set(['ms1', 'n1']), all_nodes)

            self.assertFalse(self.pc._trigger_puppet.called)
            self.assertEqual(set(), result)

        # concurrency > len(applying) and
        # len(untriggered - applying) = concurrency - len(applying)
        # trigger_puppet should be called with all nodes from untriggered (n1 and n2)
        with patch('litp.core.rpc_commands.PuppetCatalogRunProcessor.'
                   'PUPPET_CONCURRENCY', 3):
            self.pc._trigger_puppet = MagicMock(return_value=set(['n1', 'n2']))
            self.pc._get_applying_nodes = MagicMock(side_effect=[set(['ms1']),
                                                                 set(['n1', 'n2'])])
            result = self.pc._trigger_puppet_with_concurrency(
                set(['ms1', 'n1', 'n2']), all_nodes)

            self.pc._trigger_puppet.assert_called_with(set(['n1', 'n2']))
            self.assertEqual(set(['n1', 'n2']), result)

        # concurrency > len(applying nodes) and
        # len(untriggered - applying) > concurrency - len(applying)
        # trigger_puppet should be called with 2 nodes from untriggered (n1, n2, n3)
        with patch('litp.core.rpc_commands.PuppetCatalogRunProcessor.'
                   'PUPPET_CONCURRENCY', 3):

            def trigger_puppet(nodes_to_trigger):
                return nodes_to_trigger

            self.pc._trigger_puppet = MagicMock(side_effect=trigger_puppet)
            self.pc._get_applying_nodes = MagicMock(side_effect=[set(['ms1']),
                                                                 set(['n1', 'n2'])])
            result = self.pc._trigger_puppet_with_concurrency(
                set(['ms1', 'n1', 'n2', 'n3']), all_nodes)

            self.assertEqual(2, len(result))
            self.assertTrue('ms1' not in result)

        # concurrency > len(applying nodes) and
        # len(untriggered - applying) < concurrency - len(applying)
        # trigger_puppet should be called with n1
        with patch('litp.core.rpc_commands.PuppetCatalogRunProcessor.'
                   'PUPPET_CONCURRENCY', 5):
            self.pc._trigger_puppet = MagicMock(return_value=set(['n1']))
            self.pc._get_applying_nodes = MagicMock(side_effect=[set(['ms1']),
                                                                 set(['n1'])])
            result = self.pc._trigger_puppet_with_concurrency(
                set(['ms1', 'n1']), all_nodes)

            self.pc._trigger_puppet.assert_called_with(set(['n1']))
            self.assertEqual(set(['n1']), result)

    def test_trigger_puppet_with_concurrency_rpcexecution_exception(self):
        self.pc._trigger_puppet = MagicMock()
        self.pc._get_applying_nodes = \
            MagicMock(side_effect=RpcExecutionException("Error"))
        all_nodes = ['ms1', 'n1', 'n2']
        result = self.pc._trigger_puppet_with_concurrency(
            set(['ms1', 'n1']), all_nodes)
        self.assertFalse(self.pc._trigger_puppet.called)
        self.assertEqual(set(), result)

    def test_trigger_puppet_with_concurrency_mcorunerror_exception(self):
        self.pc._trigger_puppet = MagicMock()
        self.pc._get_applying_nodes = \
            MagicMock(side_effect=rpc_commands.McoRunError("Error"))
        all_nodes = ['ms1', 'n1', 'n2']

        result = self.pc._trigger_puppet_with_concurrency(
            set(['ms1', 'n1']), all_nodes)
        self.assertFalse(self.pc._trigger_puppet.called)
        self.assertEqual(set(), result)

    def test_get_applying_nodes(self):
        # All idling
        self.pc._refresh_node_stats_lockfile = MagicMock(
            return_value={'ms1': False, 'n1': False, 'n2': False}
        )
        all_nodes = ['ms1', 'n1', 'n2']
        self.assertEqual(self.pc._get_applying_nodes(all_nodes), set())

        #ms1 and n2 applying
        self.pc._refresh_node_stats_lockfile = MagicMock(
            return_value={'ms1': True, 'n1': False, 'n2': True}
        )
        all_nodes = ['ms1', 'n1', 'n2']
        self.assertEqual(self.pc._get_applying_nodes(all_nodes),
                         set(['ms1', 'n2']))

    @patch('litp.core.rpc_commands._run_process',
           MagicMock(return_value=("ms1 n1 n2 n3", "")))
    def test_find_all_nodes(self):
        self.pc._find_all_nodes = self.pc._find_all_nodes_orig
        self.assertEqual(['ms1', 'n1', 'n2', 'n3'],  self.pc._find_all_nodes())


class TestPuppetMcoProcessor(TestCase):
    def setUp(self):
        self.mco_processor = rpc_commands.PuppetMcoProcessor()
        self.mco_processor._wait = MagicMock()

        self.mco_processor.MCO_ACTION_CONCURRENCY = 2
        self.mco_processor.MCO_ACTION_WAIT_BETWEEN_RETRIES = 0.0001 # seconds
        self.mco_processor.MCO_CLI_TIMEOUT = 0.001  # seconds
        self.mco_processor.PUPPET_RUN_TOTAL_TIMEOUT = 0.1  # seconds

    def test_litpcds_11610_run_puppet_with_unreachable_node(self):
        """
        Test if the interface of run_puppet isn't changed by an exception being
        raised.

        """
        MAX_TRIES = 15
        hostnames = ['node1', 'node2']
        expected = {'node1': {'errors': ''}, 'node2': {'errors': 'Ugly error'}}
        results = [expected for _ in range(MAX_TRIES)]

        self.mco_processor._run_puppet_command = Mock(
                side_effect=give_results(results))

        ret = self.mco_processor.run_puppet(
                hostnames, "agent", "cmd", action_kwargs={})

        self.assertEquals(expected, ret)

    def test_litpcds_13803_service_killed(self):
        hostnames = ['node1', 'node2']
        expected = {'node1': {'errors': 'Litp service has been killed'},
                'node2': {'errors': 'Litp service has been killed'}}
        with patch('litp.core.rpc_commands.PuppetMcoProcessor._is_litp_killed', MagicMock(return_value=True)):
            ret = self.mco_processor.run_puppet(
                hostnames, "agent", "cmd", action_kwargs={})
        self.assertEquals(expected, ret)

    def test_litpcds_13803_service_killed_2nd_loop(self):
        hostnames = ['node1', 'node2', 'node3', 'node4']
        expected = {'node1': {'errors': ''},
        'node3': {'errors': 'Litp service has been killed'},
        'node2': {'errors': ''},
        'node4': {'errors': 'Litp service has been killed'}}
        returns = [False, True]
        answers = [{'node1': {'errors': ''}, 'node2': {'errors': ''}}]

        def side_effect(*args):
            return returns.pop(0)

        self.mco_processor._run_puppet_command = Mock(
                side_effect=give_results(answers))

        with patch('litp.core.rpc_commands.PuppetMcoProcessor._is_litp_killed',
                MagicMock(side_effect=side_effect)):
            ret = self.mco_processor.run_puppet(
                    hostnames, "agent", "cmd", action_kwargs={})

        self.assertEquals(expected, ret)

    def test_run_puppet_already_applying(self):
        # LITPCDS-12468: _run_puppet() continues if runonce issued and
        # puppet is already applying manifest
        mco_processor = rpc_commands.PuppetMcoProcessor()
        mco_processor.MCO_ACTION_WAIT_BETWEEN_RETRIES = 0.001
        mco_processor.MCO_ACTION_CONCURRENCY = 2

        err = "node unreachable"
        applying = 'node: Puppet is currently applying a catalog, cannot run now'
        # Host 'a' will pass 1st time, 'b' & 'c' will need to be retried, 'd'
        # will pass, 'e' will be retried, 'b' will pass 2nd time, 'c' & 'e' will fail
        # again, then 'c' & 'e' will pass 3rd time round.
        returns = [
            {
                "a": {"errors": applying},
                "b": {"errors": err},
            },
            {
                "c": {"errors": err},
                "d": {"errors": ""},
            },
            {
                "e": {"errors": err},
            },
            {
                "b": {"errors": applying},
                "c": {"errors": err},
            },
            {
                "e": {"errors": err},
            },
            {
                "c": {"errors": ""},
                "e": {"errors": applying},
            }
        ]

        def side_effect(*args):
            return returns.pop(0)
        mco_processor._run_puppet_command = Mock(side_effect=side_effect)
        mco_processor.runonce_puppet(["a", "b", "c", "d", "e"])
        # Applying mco response, is not treated like an error
        self.assertEquals(
            [
                call(["a", "b"], "puppet", "runonce", None),
                call(["c", "d"], "puppet", "runonce", None),
                call(["e"], "puppet", "runonce", None),
                call(["b", "c"], "puppet", "runonce", None),
                call(["e"], "puppet", "runonce", None),
                call(["c", "e"], "puppet", "runonce", None),
            ],
            mco_processor._run_puppet_command.call_args_list
        )

    def test_run_puppet_when_litp_service_is_stopped(self):
        # LITPCDS-13762 "service litpd stop" took 2 mins when nodes aren't contactable
        mco_processor = rpc_commands.PuppetMcoProcessor()
        mco_processor.MCO_ACTION_WAIT_BETWEEN_RETRIES = 0.001
        mco_processor.MCO_ACTION_CONCURRENCY = 2

        err = "node unreachable"
        applying = 'node: Puppet is currently applying a catalog, cannot run now'
        returns = [
            {
                "a": {"errors": applying},
                "b": {"errors": applying},
            },
            {
                "c": {"errors": ""},
                "d": {"errors": ""},
            },
            {
                "e": {"errors": applying},
            },
            {
                "b": {"errors": err},
                "c": {"errors": err},
            },
            {
                "e": {"errors": err},
            },
            {
                "c": {"errors": ""},
                "e": {"errors": err},
            }
        ]

        def side_effect(*args):
            return returns.pop(0)

        mco_processor._run_puppet_command = Mock(side_effect=side_effect)
        mco_processor.runonce_puppet(["a", "b", "c", "d", "e"])
        self.assertEquals(
            [
                call(["a", "b"], "puppet", "runonce", None),
                call(["c", "d"], "puppet", "runonce", None),
                call(["e"], "puppet", "runonce", None)
            ],
            mco_processor._run_puppet_command.call_args_list
        )
        # If litp service is killed/stopped, node re-tries are avoided
        mco_processor._run_puppet_command.reset_mock()
        with patch('litp.core.rpc_commands.PuppetMcoProcessor._is_litp_killed', MagicMock(return_value=True)):
            mco_processor.runonce_puppet(["a", "b", "c", "d", "e"])
        # Applying mco response, is not treated like an error
        self.assertEquals(
            [],
            mco_processor._run_puppet_command.call_args_list
        )

    def test_non_ASCII_unicode_in_stdout(self):

        path_to_raw_UTF8_json = os.path.join(os.path.dirname(__file__), "raw_UTF8.json")
        with open(path_to_raw_UTF8_json, 'r') as raw_output:
            mock_run_process = MagicMock(return_value=(raw_output.read(), ""))

            with patch('litp.core.rpc_commands._run_process', mock_run_process):
                result = rpc_commands.run_rpc_command(
                    ['node1', 'node2'],
                    'enminst',
                    'check_service',
                    { 'service': 'rhq-agent' }
                )
                self.assertTrue(isinstance(result, dict))
                self.assertTrue(all(isinstance(key, str) for key in result))
                self.assertEquals(
                    set(["node1", "node2"]),
                    set(result)
                )
                #
                self.assertTrue(isinstance(result["node1"], dict))
                self.assertEquals(set(["data", "errors"]), set(result["node1"]))

                self.assertTrue(isinstance(result["node1"]["errors"], unicode))
                self.assertEquals(u"", result["node1"]["errors"])
                #
                self.assertTrue(isinstance(result["node1"]["data"], dict))
                node1_data = result["node1"]["data"]
                self.assertTrue(isinstance(node1_data["out"], unicode))
                self.assertTrue(node1_data["out"].startswith(u"\u5fa9\u9ec3\u9762"))
                #
                self.assertTrue(isinstance(node1_data["err"], unicode))
                self.assertEquals(u"", node1_data["err"])

                # Node2 has errors!
                self.assertTrue(isinstance(result["node2"], dict))
                self.assertEquals(set(["data", "errors"]), set(result["node2"]))

                self.assertTrue(isinstance(result["node2"]["errors"], unicode))
                self.assertTrue(result["node2"]["errors"].startswith(u"node2: \u5fa9\u9ec3\u9762"))
                #
                self.assertTrue(isinstance(result["node2"]["data"], dict))
                node2_data = result["node2"]["data"]
                # This should always be unicode, even if it's all 7bit ASCII characters
                self.assertTrue(isinstance(node2_data["out"], unicode))
                self.assertEquals(u"plain old ASCII text", node2_data["out"])
                #
                self.assertTrue(isinstance(node2_data["err"], unicode))
                self.assertTrue(node2_data["err"].startswith(u"\u5fa9\u9ec3\u9762"))
