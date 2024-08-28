import unittest
import mock
import urlparse
import json

from httplib import BadStatusLine
from litp.core.task import ConfigTask
from litp.core.puppetdb_api import PuppetDbApi
from litp.core.exceptions import FailedTasklessPuppetEvent


class TestPuppetDbApi(unittest.TestCase):

    def setUp(self):
        self.api = PuppetDbApi()

    def tearDown(self):
        pass

    def test_two_events_one_resource(self):
        # 2 events for the one resource. 1st event fails,
        # 2nd event success => Task report = fail
        # E.g. update a file resouce with new 'content' and 'mode' parameters
        events = [
            {
              "status" : "fail",
              "timestamp" : "2016-08-25T10:51:30.557Z",
              "certname" : "ms1",
              'containing-class': u'Task_ms1__file__bar',
              'containment-path': [u'Stage[main]',
                                    u'Task_ms1__file__bar',
                                    u'File[bar]'],
              "report" : "70680704ebe22ce24ac88add3f40283a9492ad4d",
              "run-start-time" : "2016-08-25T10:50:51.582Z",
              "resource-title" : "bar",
              "configuration-version" : "2016-08-24 17:24:51.257138",
              "run-end-time" : "2016-08-25T10:51:25.437Z",
              "property" : "content",
              "message" : "content changed '{md5}ab07acbb1e496801937adfa772424bf7' to '{md5}1fcf0e590364d652ab438b89e1f56e4e'",
              "new-value" : "{md5}1fcf0e590364d652ab438b89e1f56e4e",
              "old-value" : "{md5}ab07acbb1e496801937adfa772424bf7",
              "line" : 6,
              "file" : "/opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ms1.pp",
              "report-receive-time" : "2016-08-25T10:51:48.995Z",
              "resource-type" : "File"
            }, {
              "status" : "success",
              "timestamp" : "2016-08-25T10:51:30.621Z",
              "certname" : "ms1",
              'containing-class': u'Task_ms1__file__bar',
              'containment-path': [u'Stage[main]',
                                    u'Task_ms1__file__bar',
                                    u'File[bar]'],
              "report" : "70680704ebe22ce24ac88add3f40283a9492ad4d",
              "run-start-time" : "2016-08-25T10:50:51.582Z",
              "resource-title" : "bar",
              "configuration-version" : "2016-08-24 17:24:51.257138",
              "run-end-time" : "2016-08-25T10:51:25.437Z",
              "property" : "mode",
              "message" : "mode changed '0644' to '0755'",
              "new-value" : "755",
              "old-value" : "644",
              "line" : 6,
              "file" : "/opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ms1.pp",
              "report-receive-time" : "2016-08-25T10:51:48.995Z",
              "resource-type" : "File"
            }
        ]
        event_resources = [
            {
              "certname" : "ms1",
              "resource" : "cee9a01c805178ecea703dddf6608175fe103aee",
              "title" : "bar",
              "parameters" : {
                "content" : "spam eggs",
                "ensure" : "file",
                "mode" : "0755",
                "owner" : [ "root", "litp-admin" ]
              },
              "type" : "File",
              "exported" : False,
              "line" : 6,
              "file" : "/opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ms1.pp",
              'tags': [u'node',
                   u'bar',
                   u'file',
                   u'ms1',
                   u'tuuid_99bf6bea-6477-471a-896c-1f67dab1622c',
                   u'task_ms1__file__bar',
                   u'class'],
            }
        ]
        with mock.patch.object(self.api, '_query', mock.Mock(return_value=event_resources)):
            # Assert one call to query as resouce has already been encountered
            known_tasks_dict, taskless_failures = self.api._get_reports_resources(events)
            expected = [mock.call('resources', ['and', ['=', 'title', u'bar'],
                ['=', 'type', u'File'], ['=', 'certname', u'ms1']])]
            self.assertEqual(expected, self.api._query.call_args_list)
            # Assert one known task for the one resource, with two event states
            expected_known_tasks = {
                    (u'task_ms1__file__bar', u'tuuid_99bf6bea-6477-471a-896c-1f67dab1622c'):
                    [(event_resources[0], "fail"), (event_resources[0], "success")]}
            self.assertEquals(expected_known_tasks, known_tasks_dict)
            self.assertFalse(taskless_failures)
            # Assert that you get one task report with a failed state
            event_tasks_report = self.api._build_report(known_tasks_dict)
            expected = u'litp_feedback:task_ms1__file__bar:tuuid_99bf6bea-6477-471a-896c-1f67dab1622c=fail,'
            self.assertEquals(event_tasks_report, expected)

    def test_build_no_event_report(self):
        # Assert that only unencountered tasks in the plan have reports built
        event_resource = {
              u'certname': u'ms1',
              u'exported': False,
              u'file': u'/opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ms1.pp',
              u'line': 531,
              u'parameters': {u'ensure': u'installed',
                              u'require': [],
                              u'tag': u'tuuid_9eb295e6-4d69-46dc-b942-b4d4be242572'},
              u'resource': u'6121f312789a035216526db12543ab26029887b1',
              u'tags': [u'node',
                        u'package',
                        u'task_ms1__package__namo',
                        u'ms1',
                        u'namo',
                        u'tuuid_9eb295e6-4d69-46dc-b942-b4d4be242572',
                        u'class'],
              u'title': u'namo',
              u'type': u'Package'
        }
        all_resources = [
            {u'certname': u'ms1',
              u'exported': False,
              u'file': u'/opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ms1.pp',
              u'line': 531,
              u'parameters': {u'ensure': u'installed',
                              u'require': [],
                              u'tag': u'tuuid_9eb295e6-4d69-46dc-b942-b4d4be242572'},
              u'resource': u'6121f312789a035216526db12543ab26029887b1',
              u'tags': [u'node',
                        u'package',
                        u'task_ms1__package__namo',
                        u'ms1',
                        u'namo',
                        u'tuuid_9eb295e6-4d69-46dc-b942-b4d4be242572',
                        u'class'],
              u'title': u'namo',
              u'type': u'Package'},
             {u'certname': u'ms1',
              u'exported': False,
              u'file': u'/opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ms1.pp',
              u'line': 531,
              u'parameters': {u'ensure': u'installed',
                              u'require': [],
                              u'tag': u'tuuid_99bf6bea-6477-471a-896c-1f67dab1622c'},
              u'resource': u'855b71e01851f010bca72f85e397730dee3c322a',
              u'tags': [u'node',
                        u'telnet',
                        u'package',
                        u'ms1',
                        u'tuuid_99bf6bea-6477-471a-896c-1f67dab1622c',
                        u'task_ms1__package__telnet',
                        u'class'],
              u'title': u'telnet',
              u'type': u'Package'}
        ]
        known_tasks_dict = {
                (u'task_ms1__package__namo', u'tuuid_9eb295e6-4d69-46dc-b942-b4d4be242572'):
                [(event_resource, "fail")]}
        # Assert that the resource which we recieved an event for does not return a task report
        # when building eventless task reports
        self.assertEqual(
            'litp_feedback:task_ms1__package__telnet:tuuid_99bf6bea-6477-471a-896c-1f67dab1622c=success,',
            self.api._build_no_event_report(all_resources, known_tasks_dict))

    def test_two_resources_same_task_tag(self):
        # TORF-143098: 2 resources, same task tag, one fail one success => report fails task
        event_resource = {
              u'certname': u'ms1',
              u'exported': False,
              u'file': u'/opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ms1.pp',
              u'line': 531,
              u'parameters': {u'ensure': u'installed',
                              u'require': [],
                              u'tag': u'tuuid_9eb295e6-4d69-46dc-b942-b4d4be242572'},
              u'resource': u'6121f312789a035216526db12543ab26029887b1',
              u'tags': [u'node',
                        u'package',
                        u'task_ms1__package__namo',
                        u'ms1',
                        u'namo',
                        u'tuuid_9eb295e6-4d69-46dc-b942-b4d4be242572',
                        u'class'],
              u'title': u'namo',
              u'type': u'Package'
        }
        all_resources = [
            {u'certname': u'ms1',
              u'exported': False,
              u'file': u'/opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ms1.pp',
              u'line': 531,
              u'parameters': {u'ensure': u'installed',
                              u'require': [],
                              u'tag': u'tuuid_9eb295e6-4d69-46dc-b942-b4d4be242572'},
              u'resource': u'6121f312789a035216526db12543ab26029887b1',
              u'tags': [u'node',
                        u'package',
                        u'task_ms1__package__namo',
                        u'ms1',
                        u'namo',
                        u'tuuid_9eb295e6-4d69-46dc-b942-b4d4be242572',
                        u'class'],
              u'title': u'namo',
              u'type': u'Package'},
             {u'certname': u'ms1',
              u'exported': False,
              u'file': u'/opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ms1.pp',
              u'line': 531,
              u'parameters': {u'ensure': u'installed',
                              u'require': [],
                              u'tag': u'tuuid_99bf6bea-6477-471a-896c-1f67dab1622c'},
              u'resource': u'855b71e01851f010bca72f85e397730dee3c322a',
              u'tags': [u'node',
                        u'telnet',
                        u'package',
                        u'ms1',
                        u'tuuid_9eb295e6-4d69-46dc-b942-b4d4be242572',
                        u'task_ms1__package__namo',
                        u'class'],
              u'title': u'telnet',
              u'type': u'Package'}
        ]
        # The resource event fails
        known_tasks_dict = {
                (u'task_ms1__package__namo', u'tuuid_9eb295e6-4d69-46dc-b942-b4d4be242572'):
                [(event_resource, "fail")]}
        event_tasks_report = self.api._build_report(known_tasks_dict)
        expected = u'litp_feedback:task_ms1__package__namo:tuuid_9eb295e6-4d69-46dc-b942-b4d4be242572=fail,'
        self.assertEquals(expected, event_tasks_report)
        # As both resources have the same task, there are no eventless reports to be created
        no_event_tasks_report = self.api._build_no_event_report(all_resources, known_tasks_dict)
        self.assertEquals('', no_event_tasks_report)

    def test_two_resources_same_task_tag_only_one_feedback(self):
        # 2 event resources for the same task, one fails, other success, only one litp feedback generated
        # Nas / Network IT failures
        event_resources = [{
              u'certname': u'ms1',
              u'exported': False,
              u'file': u'/opt/ericsson/nms/litp/etc/puppet/manifests/plugins/ms1.pp',
              u'line': 531,
              u'parameters': {u'ensure': u'installed',
                              u'require': [],
                              u'tag': u'tuuid_9eb295e6-4d69-46dc-b942-b4d4be242572'},
              u'resource': u'6121f312789a035216526db12543ab26029887b1',
              u'tags': [u'node',
                        u'package',
                        u'task_ms1__package__namo',
                        u'ms1',
                        u'namo',
                        u'tuuid_9eb295e6-4d69-46dc-b942-b4d4be242572',
                        u'class'],
              u'title': u'namo',
              u'type': u'Package'
          },
          {
              u'certname': u'node1',
              u'exported': False,
              u'file': u'/opt/ericsson/nms/litp/etc/puppet/manifests/plugins/node1.pp',
              u'line': 631,
              u'parameters': {u'ensure': u'installed',
                              u'require': [],
                              u'tag': u'tuuid_9eb295e6-4d69-46dc-b942-b4d4be242572'},
              u'resource': u'IM_A_DIFFERENT_RESOURCE',
              u'tags': [u'node',
                        u'package',
                        u'task_ms1__package__namo',
                        u'ms1',
                        u'namo',
                        u'tuuid_9eb295e6-4d69-46dc-b942-b4d4be242572',
                        u'class'],
              u'title': u'ifcfg-eth2',
              u'type': u'Exec'
            }
        ]
        # One of the events for the same resource fails
        known_tasks_dict = {
                (u'task_ms1__package__namo', u'tuuid_9eb295e6-4d69-46dc-b942-b4d4be242572'):
                [(event_resources[0], "fail"), (event_resources[1], "success")]}
        expected = u'litp_feedback:task_ms1__package__namo:tuuid_9eb295e6-4d69-46dc-b942-b4d4be242572=fail,'
        feedback = self.api._build_report(known_tasks_dict)
        self.assertEquals(expected, feedback)

    @mock.patch('litp.core.puppetdb_api.PuppetDbApi._get_eventless_tasks', mock.Mock(return_value=['task_uid']))
    @mock.patch('litp.core.puppetdb_api.PuppetDbApi._build_no_event_report', mock.Mock(return_value=""))
    @mock.patch('litp.core.puppetdb_api.PuppetDbApi._build_report', mock.Mock(return_value=""))
    @mock.patch('litp.core.puppetdb_api.PuppetDbApi._get_reports_resources', mock.Mock(return_value=({}, set([]))))
    @mock.patch('litp.core.puppetdb_api.PuppetDbApi._get_report_events', mock.Mock())
    @mock.patch('litp.core.puppetdb_api.PuppetDbApi._get_node_resources')
    @mock.patch('litp.core.puppetdb_api.PuppetDbApi._get_reports')
    def test_use_lowercase_hostnames_for_queries(self, m_get_reports, m_get_node_resources):
        # TORF-143394: Puppet DB Api expects lowercase certnames
        litp_hostname = "MarS1"
        certname, config_version, tasks_report, taskless_failures = self.api.check_for_feedback(
                litp_hostname, 123, [mock.Mock()])
        # Assert that the lowercase certname is returned for the litp report
        self.assertEquals(certname, "mars1")
        # Assert that the certname used for queries has been lowercased
        expected_get_reports =[mock.call("mars1", 123)]
        expected_get_node_res =[mock.call("mars1")]
        self.assertEqual(expected_get_reports, m_get_reports.call_args_list)
        self.assertEqual(expected_get_node_res, m_get_node_resources.call_args_list)

    @mock.patch('litp.core.puppetdb_api.urlopen')
    def test_path_to_urlopen(self, mock_url_open):
        # Assert that url_open is called with the correct url and params
        query = ['=', 'certname', u'ms1'] 
        self.api._query('reports', query)
        expected_path = 'http://localhost:8080/v3/reports?query=%5B%22%3D%22%2C+%22certname%22%2C+%22ms1%22%5D'
        # Assert expected path used
        self.assertEquals(mock_url_open.call_args_list, [mock.call(expected_path)])
        # Assert expected params used
        actual_path = mock_url_open.call_args_list[0][0][0]
        actual_parsed_params = urlparse.parse_qs(actual_path)
        actual_params = json.loads(actual_parsed_params['http://localhost:8080/v3/reports?query'][0])
        self.assertEqual(actual_params, query)

    def test_get_task_uids(self):
        # Assert that a resource with task uids tags, returns the task uid, uuid
        task_resource = {
            u'certname': u'ms1',
            u'tags': [u'node',
                      u'telnet',
                      u'package',
                      u'ms1',
                      u'tuuid_99bf6bea-6477-471a-896c-1f67dab1622c',
                      u'task_ms1__package__telnet',
                      u'class',
                      u'foo'],
            u'title': u'telnet',
            u'type': u'Package'
        }
        uid, uuid = self.api._get_task_uids(task_resource)
        self.assertEqual(u'task_ms1__package__telnet', uid)
        self.assertEqual( u'tuuid_99bf6bea-6477-471a-896c-1f67dab1622c', uuid)

        # Assert a resource with no task tags returns None, None
        task_resource = {
            u'certname': u'ms1',
            u'tags': [u'node',
                      u'telnet',
                      u'package',
                      u'ms1',
                      u'class',
                      u'foo'],
            u'title': u'telnet',
            u'type': u'Package'
        }
        self.assertEqual((None, None), self.api._get_task_uids(task_resource))

    @mock.patch('litp.core.puppetdb_api.PuppetDbApi._query')
    def test_get_reports(self, mock_query):
        # Assert that only the reports for the correct config_version is returned
        all_reports = [
            {u'certname': u'ms1',
               u'configuration-version': u'2010: 1-2-3 4:5.6 z',
              u'end-time': u'2016-08-22T10:14:18.500Z',
              u'hash': u'32db5d3abaaac146961c8688888888888801c22b',
              u'puppet-version': u'3.3.2',
              u'receive-time': u'2016-08-22T10:14:58.143Z',
              u'report-format': 4,
              u'start-time': u'2016-08-22T10:13:53.669Z',
              u'transaction-uuid': u'5f767fe5-cc39-8888-8885-628af64c470b'
            },
            {u'certname': u'ms1',
              u'configuration-version': u'13',
              u'end-time': u'2016-08-22T10:12:12.500Z',
              u'hash': u'32db5d3abaaac146961c864c6ece177777777',
              u'puppet-version': u'3.3.2',
              u'receive-time': u'2016-08-22T10:13:48.143Z',
              u'report-format': 4,
              u'start-time': u'2016-08-22T10:12:23.669Z',
              u'transaction-uuid': u'5f767fe5-cc39-1234-b905-628af64c470b'
            },
            {u'certname': u'ms1',
              u'configuration-version': u'14',
              u'end-time': u'2016-08-22T10:14:12.500Z',
              u'hash': u'32db5d3abaaac146961c864c6ece10280d01c22b',
              u'puppet-version': u'3.3.2',
              u'receive-time': u'2016-08-22T10:14:48.143Z',
              u'report-format': 4,
              u'start-time': u'2016-08-22T10:13:23.669Z',
              u'transaction-uuid': u'5f767fe5-cc39-5677-b905-628af64c470b'
            },
            {u'certname': u'ms1',
              u'configuration-version': u'15',
              u'end-time': u'2016-08-22T11:14:12.500Z',
              u'hash': u'32db5d3abaaac146961c864c6ece10280d12222',
              u'puppet-version': u'3.3.2',
              u'receive-time': u'2016-08-22T10:14:58.143Z',
              u'report-format': 4,
              u'start-time': u'2016-08-22T10:13:23.669Z',
              u'transaction-uuid': u'5f767fe5-cc39-4973-b905-628af64c470b'
            }
        ]
        mock_query.return_value = all_reports
        actual_reports = self.api._get_reports("ms1", 14)
        self.assertEqual([mock.call("reports", ["=", "certname", "ms1"])],
            mock_query.call_args_list)
        self.assertEqual(actual_reports, all_reports[2:])

    @mock.patch('litp.core.puppetdb_api.PuppetDbApi._query')
    def test_get_report_events(self, mock_query):
        all_reports = [
            {u'certname': u'ms1',
              u'configuration-version': u'1-2-3 4:5.6',
              u'hash': u'32db5d3abaaac146961c864c6ece10280d01c22b',
            },
            {u'certname': u'ms1',
              u'configuration-version': u'1-2-3 4:5.6',
              u'hash': u'32db5d3abaaac146961c86888888888888',
            }
        ]
        response1 = [{
                u'certname': u'ms1',
                u'configuration-version': u'2016-08-22 11:13:17.207680',
                u'report': u'32db5d3abaaac146961c864c6ece10280d01c22b',
                u'resource-title': u'telnet',
                u'resource-type': u'Package',
                u'status': u'success'
                },
                {
                u'certname': u'ms1',
                u'configuration-version': u'2016-08-22 11:13:17.207680',
                u'report': u'32db5d3abaaac146961c86888888888888',
                u'resource-title': u'nano',
                u'resource-type': u'Package',
                u'status': u'success'
        }]
        response2 = [{
                u'certname': u'ms1',
                u'configuration-version': u'2016-08-22 11:13:17.207680',
                u'report': u'32db5d3abaaac146961c864c6ece10280d01c22b',
                u'resource-title': u'mutt',
                u'resource-type': u'Package',
                u'status': u'success'
        }]
        events = [response1, response2]

        mock_query.side_effect = lambda endpoint, query: events.pop()
        actual_events = self.api._get_report_events(all_reports)
        self.assertEqual([
            mock.call("events", ["=", "report", "32db5d3abaaac146961c864c6ece10280d01c22b"]),
            mock.call("events", ["=", "report", "32db5d3abaaac146961c86888888888888"])],
            mock_query.call_args_list)
        self.assertEqual(actual_events, response2 + response1)

    def test_get_eventless_tasks(self):
        # Assert that the eventless task is detected and returned from phase
        event_task = ConfigTask(mock.Mock(hostname="ms1"), mock.Mock(), "Desc", "package", "telnet")
        eventless_task = ConfigTask(mock.Mock(), mock.Mock(), "Desc2", "package", "nano")
        phase = [event_task, eventless_task]
        known_tasks_dict = {("task_%s" % event_task.unique_id, "tuuid_%s" % event_task.uuid): [mock.Mock()]} 
        actual_eventless_tasks = self.api._get_eventless_tasks(known_tasks_dict, phase)
        self.assertEqual([eventless_task], actual_eventless_tasks)

    @mock.patch('litp.core.puppetdb_api.PuppetDbApi._query')
    def test_get_reports_resources(self, mock_query):
        mock_query.return_value = [{'foo': 'bar'}]
        # Test that resource with no uid or uuids doesn't get into known_tasks_dict
        events = [{"resource-title": "foo", "resource-type": "Package",
            "certname": "ms1", "status": "success"}]
        with mock.patch("litp.core.puppetdb_api.PuppetDbApi._get_task_uids",
                mock.Mock(return_value=(None, None))):
            known_tasks_dict, taskless_failures = self.api._get_reports_resources(events)
            self.assertEquals({}, known_tasks_dict)
            self.assertFalse(taskless_failures)

    def test_query_exceptions(self):
        # TORF-147530: httplib.BadStatusLine Exception thrown
        query = ['=', 'certname', u'ms1']
        with mock.patch('litp.core.puppetdb_api.urlopen', mock.Mock(
                side_effect=BadStatusLine('foo'))):
            self.assertEquals([], self.api._query('reports', query))

        # All Exceptions will be caught
        with mock.patch('litp.core.puppetdb_api.urlopen', mock.Mock(
                side_effect=Exception('foo'))):
            self.assertEquals([], self.api._query('reports', query))

        # Assert that json.loads() Exceptions are also caught
        with mock.patch('litp.core.puppetdb_api.urlopen') as mock_url_open:
            mock_url_open.return_value = mock.Mock(read=lambda: 'Not Found')
            self.assertEquals([], self.api._query('reports', query))

    @mock.patch('litp.core.puppetdb_api.PuppetDbApi._build_task_report', mock.Mock(return_value="XXX"))
    @mock.patch('litp.core.puppetdb_api.PuppetDbApi._get_task_uids', mock.Mock(return_value=(None, None)))
    def test_resource_with_no_task_tags(self):
        # Resource queried from PuppetDb with no litp task tags
        # Fails in puppet_manager.format_report -> IndexError on split
        all_resources = [{"foo": "bar"}]
        known_tasks_dict = {}
        report = self.api._build_no_event_report(all_resources, known_tasks_dict)
        self.assertEquals(report, '')

    def test_check_config_version(self):
        self.assertTrue(self.api.check_config_version('4', 4))
        self.assertTrue(self.api.check_config_version('5', 4))
        self.assertFalse(self.api.check_config_version('3', 4))
        self.assertFalse(self.api.check_config_version('2016: 09-09 T 20:00', 4))

    @mock.patch('litp.core.puppetdb_api.PuppetDbApi._query')
    def test_failed_event_for_taskless_resource(self, m_query):
        all_events = [
            {
              "report" : "a7002e216782c2a47397d0fad72ec09370483993",
              "status" : "failure",
              "resource-title" : "/opt/mcollective/mcollective/util",
              "resource-type" : "File",
              "certname" : "node1",
              "new-value" : "null",
              "old-value" : "null",
              "line" : 64,
              "file" : "/opt/ericsson/nms/litp/etc/puppet/modules/litp/manifests/mn_node.pp",
              "property" : "",
              "message": "Connection timed out - connect(2) Could not retrieve file metadata for puppet:///modules/mcollective_utils: Connection timed out - connect(2)",
              'containing-class': u'',

              'containment-path': [u'Stage[main]',
                                    u'Task_ms1__file__bar',
                                    u'File[bar]'],

              "timestamp" : "2016-08-25T10:51:30.557Z",
              "run-start-time" : "2016-08-25T10:50:51.582Z",
              "configuration-version" : "2016-08-24 17:24:51.257138",
              "run-end-time" : "2016-08-25T10:51:25.437Z",
              "report-receive-time" : "2016-08-25T10:51:48.995Z",
            },
        ]
        m_query.return_value = []
        known_tasks_dict, taskless_failures = self.api._get_reports_resources(all_events)
        self.assertTrue(taskless_failures)
        self.assertEquals({}, known_tasks_dict)
