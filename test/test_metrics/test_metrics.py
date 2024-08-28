import copy
import mock
import tempfile
import time
import unittest
import pwd
import grp
from litp.xml.xml_exporter import XmlExporter
from litp.core.execution_manager import ExecutionManager
from litp.core.model_manager import ModelManager
from litp.core.plan import Plan
from litp.core.task import (CallbackTask, RemoteExecutionTask, ConfigTask,
    CleanupTask)
from litp.enable_metrics import apply_metrics
from litp.metrics import (metrics_logger, metrics_patch, MetricsLogger, logger,
                          set_handlers, OwnedWatchedFileHandler)


class DummyDoer(object):
    def do(self, *args, **kwargs):
        return 'Doing!', args, kwargs

    def do_raise(self, *args, **kwargs):
        raise Exception(args, kwargs)


class TestMetricsLogger(unittest.TestCase):
    def setUp(self):
        self.logfile = tempfile.NamedTemporaryFile(prefix='tmpTest')
        self.test_am = copy.deepcopy(apply_metrics)
        self.backup_am = copy.deepcopy(apply_metrics)

    def tearDown(self):
        # Removing handlers, so that logfile.close actually closes and removes
        # the file. Otherwise the tmp file never gets removed.
        logger.handlers = []
        self.logfile.close()
        apply_metrics = self.backup_am

    @mock.patch('litp.metrics.getgrnam', mock.Mock(return_value=mock.Mock(gr_gid=0)))
    @mock.patch('litp.metrics.getpwnam', mock.Mock(return_value=mock.Mock(pw_uid=0)))
    @mock.patch('litp.core.litp_logging.os.chown', mock.Mock(return_value=True))
    def test_set_handlers(self):
        self.assertEquals(logger.handlers, [])
        set_handlers(path=self.logfile.name)
        self.assertTrue(isinstance(logger.handlers[0], OwnedWatchedFileHandler))
        self.assertEquals(len(logger.handlers), 1)

    @mock.patch('litp.metrics.log')
    @mock.patch('litp.metrics.getgrnam')
    @mock.patch('litp.metrics.getpwnam', mock.Mock(return_value=mock.Mock(pw_uid=0)))
    def test_set_handlers_exception(self, mock_get_grnam, mock_log):
        error = "No entry for user"
        key_error = KeyError(error)
        mock_get_grnam.side_effect = key_error

        self.assertEquals(logger.handlers, [])

        try:
            set_handlers(path=self.logfile.name)
        except KeyError as e:
            self.assertEquals(key_error, e)

        mock_log.trace.warning.assert_called_once_with(
            "Could not get group id for group celery "
            "or user id for user celery. {0}".
                format(str(key_error)))

        self.assertEquals(logger.handlers, [])

    @mock.patch('litp.metrics.getgrnam', mock.Mock(return_value=mock.Mock(gr_gid=0)))
    @mock.patch('litp.metrics.getpwnam', mock.Mock(return_value=mock.Mock(pw_uid=0)))
    @mock.patch('litp.core.litp_logging.os.chown', mock.Mock(return_value=True))
    def test_simple_log(self):
        set_handlers(self.logfile.name)
        self.assertEquals(self.logfile.readlines(), [])
        metrics_logger.log({'test_key': 'test_value'})
        actual = self.logfile.readlines()
        expected = [',[LITP].test_key=test_value\n']
        self.assertEquals(len(actual), 1)
        self.assertTrue(expected[0] in actual[0])

    @mock.patch('litp.metrics.getgrnam', mock.Mock(return_value=mock.Mock(gr_gid=0)))
    @mock.patch('litp.metrics.getpwnam', mock.Mock(return_value=mock.Mock(pw_uid=0)))
    @mock.patch('litp.core.litp_logging.os.chown', mock.Mock(return_value=True))
    def test_extending_loggers(self):
        self.assertEquals('[LITP]', metrics_logger.metric_prefix())
        other_logger = metrics_logger.extend_with('OtherLogger')
        self.assertEquals('[LITP][OtherLogger]', other_logger.metric_prefix())

        set_handlers(self.logfile.name)
        self.assertEquals(self.logfile.readlines(), [])
        other_logger.log({'test_key': 'test_value'})
        actual = self.logfile.readlines()
        expected = [',[LITP][OtherLogger].test_key=test_value\n']
        self.assertEquals(len(actual), 1)
        self.assertTrue(expected[0] in actual[0])

    @mock.patch('litp.metrics.getgrnam', mock.Mock(return_value=mock.Mock(gr_gid=0)))
    @mock.patch('litp.metrics.getpwnam', mock.Mock(return_value=mock.Mock(pw_uid=0)))
    @mock.patch('litp.core.litp_logging.os.chown', mock.Mock(return_value=True))
    def test_metrics_patch(self):
        def _raise():
            raise Exception('TestException')

        test_list = [1, 2, 3]

        set_handlers(self.logfile.name)

        doer = DummyDoer()
        doer.do()
        actual = doer.do(1, key='value')
        expected =  ('Doing!', (1,), {'key': 'value'})
        self.assertEquals(actual, expected)

        self.assertEquals(self.logfile.readlines(), [])

        metrics_patch(doer, 'do', metrics_logger,
                StaticKey='StaticValue',
                EvaluableKey=lambda: 'EvaluableValue',
                ExceptionalKey=_raise,
                LenKey=lambda: len(test_list))

        # Behaviour mustn't change
        actual = doer.do(1, key='value')
        expected =  ('Doing!', (1,), {'key': 'value'})
        self.assertEquals(actual, expected)

        expected = [
            ',[LITP].EvaluableKey=EvaluableValue',
            ',[LITP].ExceptionalKey=<UnableToGetMetricsValue>',
            ',[LITP].LenKey=3',
            ',[LITP].StaticKey=StaticValue',
            ',[LITP].TimeTaken=0.0',
        ]

        actual = self.logfile.readlines()
        self.assertEquals(len(actual), len(expected))
        for i, value in enumerate(expected):
            self.assertTrue(expected[i] in actual[i])

    @mock.patch('litp.metrics.getgrnam', mock.Mock(return_value=mock.Mock(gr_gid=0)))
    @mock.patch('litp.metrics.getpwnam', mock.Mock(return_value=mock.Mock(pw_uid=0)))
    @mock.patch('litp.core.litp_logging.os.chown', mock.Mock(return_value=True))
    def test_exception_from_callback(self):
        def _raise():
            raise Exception('TestException')

        set_handlers(self.logfile.name)
        doer = DummyDoer()
        metrics_patch(doer, 'do', metrics_logger,
                ExceptionalKey=_raise)
        doer.do()
        expected = [
            ',[LITP].ExceptionalKey=<UnableToGetMetricsValue>',
            ',[LITP].TimeTaken=0.0',
        ]

        actual = self.logfile.readlines()
        self.assertEquals(len(actual), len(expected))
        for i, value in enumerate(expected):
            self.assertTrue(expected[i] in actual[i])

    def test_exception_in_subject_method_isnt_silenced(self):
        doer = DummyDoer()
        metrics_patch(doer, 'do_raise', metrics_logger)
        self.assertRaises(Exception, doer.do_raise)
        # Nothing should get logged, as logs are generated after a successful
        # function call.
        expected = []
        actual = self.logfile.readlines()
        self.assertEquals(len(actual), len(expected))
        for i, value in enumerate(expected):
            self.assertTrue(expected[i] in actual[i])

    @mock.patch('litp.metrics.getgrnam', mock.Mock(return_value=mock.Mock(gr_gid=0)))
    @mock.patch('litp.metrics.getpwnam', mock.Mock(return_value=mock.Mock(pw_uid=0)))
    @mock.patch('litp.core.litp_logging.os.chown', mock.Mock(return_value=True))
    def test_sorted(self):
        def _raise():
            raise Exception('TestException')

        test_list = [1, 2, 3]

        set_handlers(self.logfile.name)

        doer = DummyDoer()
        doer.do()
        metrics_patch(doer, 'do', metrics_logger,
                StaticKey='StaticValue',
                EvaluableKey=lambda: 'EvaluableValue',
                ExceptionalKey=_raise,
                LenKey=lambda: len(test_list))
        actual = doer.do(1, key='value')
        expected = sorted([
            ',[LITP].EvaluableKey=EvaluableValue',
            ',[LITP].ExceptionalKey=<UnableToGetMetricsValue>',
            ',[LITP].LenKey=3',
            ',[LITP].StaticKey=StaticValue',
            ',[LITP].TimeTaken=0.0',
        ])
        actual = self.logfile.readlines()
        self.assertEquals(len(actual), len(expected))
        for i, value in enumerate(sorted(actual)):
            self.assertTrue(expected[i] in actual[i])

        # TimeTaken has to be always at the end of a log bulk produced by a
        # single function call.
        self.assertTrue('TimeTaken' in actual[-1])

    @mock.patch('litp.metrics.getgrnam', mock.Mock(return_value=mock.Mock(gr_gid=0)))
    @mock.patch('litp.metrics.getpwnam', mock.Mock(return_value=mock.Mock(pw_uid=0)))
    @mock.patch('litp.core.litp_logging.os.chown', mock.Mock(return_value=True))
    @mock.patch('litp.enable_metrics.xml_metrics')
    @mock.patch.object(XmlExporter, '_build_xml')
    def test_apply_metrics(self, mock_build_xml, mock_xml_metrics):
        set_handlers(self.logfile.name)

        def _build_xml():
            self.test_am.xml_metric.log({'InlineLogKey': 'InlineLogValue'})

        def xml_metrics(obj):
            am = self.test_am
            if str(type(obj)) == "<class 'litp.xml.xml_exporter.XmlExporter'>":
                am.xml_metric = (metrics_logger
                    .extend_with('XML')
                    .extend_with('Export'))
                metrics_patch(obj, '_build_xml', am.xml_metric)

        mock_xml_metrics.side_effect = xml_metrics
        mock_build_xml.side_effect = _build_xml

        xml_exporter = XmlExporter(mock.Mock)
        xml_exporter._build_xml()

        expected = sorted([
            ',[LITP][XML][Export].InlineLogKey=InlineLogValue',
            ',[LITP][XML][Export].TimeTaken=0.0',
        ])
        actual = self.logfile.readlines()
        self.assertEquals(len(actual), len(expected))
        for i, value in enumerate(actual):
            self.assertTrue(expected[i] in actual[i])

    @mock.patch('litp.metrics.getgrnam', mock.Mock(return_value=mock.Mock(gr_gid=0)))
    @mock.patch('litp.metrics.getpwnam', mock.Mock(return_value=mock.Mock(pw_uid=0)))
    @mock.patch('litp.core.litp_logging.os.chown', mock.Mock(return_value=True))
    @mock.patch('litp.enable_metrics.xml_metrics')
    @mock.patch.object(XmlExporter, '_build_xml')
    def test_metrics_patch_hooks(self, mock_build_xml, mock_xml_metrics):
        set_handlers(self.logfile.name)

        def ret_value_hook(value):
            return {'ReturnedValue': value}

        def args_value_hook(value):
            return {'ArgValue': value}

        def _build_xml(arg):
            self.test_am.xml_metric.log({'InlineLogKey': 'InlineLogValue'})
            return 'test_return_value'

        def xml_metrics(obj):
            am = self.test_am
            if str(type(obj)) == "<class 'litp.xml.xml_exporter.XmlExporter'>":
                am.xml_metric = (metrics_logger
                    .extend_with('XML')
                    .extend_with('Export'))
                metrics_patch(obj, '_build_xml', am.xml_metric,
                    return_value_hook=ret_value_hook,
                    args_hook=args_value_hook)

        mock_xml_metrics.side_effect = xml_metrics
        mock_build_xml.side_effect = _build_xml

        xml_exporter = XmlExporter(mock.Mock)
        xml_exporter._build_xml('test_argument')

        expected = [
            ',[LITP][XML][Export].InlineLogKey=InlineLogValue',
            ',[LITP][XML][Export].ArgValue=test_argument',
            ',[LITP][XML][Export].ReturnedValue=test_return_value',
            ',[LITP][XML][Export].TimeTaken=0.0',
        ]
        actual = self.logfile.readlines()
        self.assertEquals(len(actual), len(expected))
        for i, value in enumerate(actual):
            self.assertTrue(expected[i] in actual[i])

    @mock.patch('litp.metrics.getgrnam', mock.Mock(return_value=mock.Mock(gr_gid=0)))
    @mock.patch('litp.metrics.getpwnam', mock.Mock(return_value=mock.Mock(pw_uid=0)))
    @mock.patch('litp.core.litp_logging.os.chown', mock.Mock(return_value=True))
    @mock.patch('litp.enable_metrics.xml_metrics')
    @mock.patch.object(XmlExporter, '_build_xml')
    def test_logger_id_handler(self, mock_build_xml, mock_xml_metrics):
        set_handlers(self.logfile.name)
        logger_id_hook = lambda: "_test_string_"
        self.test_am.xml_metric.id_handler = logger_id_hook
        self.test_am.xml_metric.log({'Key': 'Value'})

        expected = [
            ',[LITP][XML][Export_test_string_].Key=Value',
        ]
        actual = self.logfile.readlines()
        self.assertEquals(len(actual), len(expected))
        for i, value in enumerate(actual):
            self.assertTrue(expected[i] in actual[i])

    def test_plan_creation_metrics(self):
        fake_execution_manager = mock.MagicMock(spec=ExecutionManager)
        fake_execution_manager.__module__ = 'litp.core.execution_manager'
        fake_execution_manager.plugin_manager = None
        fake_execution_manager.plan = mock.MagicMock()
        fake_execution_manager.plan.current_phase = None

        self.test_am(fake_execution_manager)
        self.assertTrue(hasattr(self.test_am, 'phase_metric'))
        phase_metric = self.test_am.phase_metric

        no_current_phase_metric_id = phase_metric.id_handler()
        self.assertTrue(isinstance(no_current_phase_metric_id, str))
        self.assertEquals('', no_current_phase_metric_id)


        fake_execution_manager.plan.current_phase = 0
        first_phase_current_id = phase_metric.id_handler()
        self.assertTrue(isinstance(first_phase_current_id, str))
        self.assertEquals('1', first_phase_current_id)

        fake_execution_manager.plan.current_phase = 1
        first_phase_current_id = phase_metric.id_handler()
        self.assertTrue(isinstance(first_phase_current_id, str))
        self.assertEquals('2', first_phase_current_id)

    @mock.patch('litp.core.plan.BasePlan._get_task_cluster', mock.Mock(return_value=None))
    @mock.patch('litp.core.execution_manager.ExecutionManager._has_errors_before_create_plan',
            mock.Mock(return_value=None))
    def test_remote_execution_tasks_create_plan(self):
        # TORF-132323: CallbackTasks / RemoteExecutionTask count error
        model_manager = ModelManager()
        execution_manager = ExecutionManager(model_manager, mock.Mock(), mock.Mock())

        mock_item =  mock.Mock()

        class MockPlugin():
            def cb(api):
                pass
        # Plan has 6 tasks: 3 CallbackTasks, 2 RemoteExecutionTask and 1 ConfigTask
        phases = [
            [
                CallbackTask(mock_item, "Desc", MockPlugin.cb),
                RemoteExecutionTask([mock.Mock(hostname="ms1")], mock_item, "Desc", "foo", "bar")
            ],
            [
                CallbackTask(mock_item, "Desc", MockPlugin.cb),
                RemoteExecutionTask([mock.Mock(hostname="ms1")], mock_item, "Desc", "spam", "eggs"),
                CallbackTask(mock_item, "Desc", MockPlugin.cb),
            ],
            [
                ConfigTask(mock_item, mock_item, "Desc", "lola", "bunny")
            ],
            [
                CleanupTask(mock_item)
            ]

        ]
        plan = Plan(phases)

        with mock.patch.object(execution_manager, '_create_plan', mock.Mock(return_value=plan)):
            with mock.patch('litp.metrics.MetricsLogger.log') as mock_log:
                execution_manager.create_plan()
                metrics = mock_log.call_args_list[0][0][0]
                self.assertEqual(7, metrics['TotalNoOfTasks'])
                self.assertEqual(3, metrics['NoOfCallbackTasks'])
                self.assertEqual(2, metrics['NoOfRemoteExecutionTasks'])
                self.assertEqual(1, metrics['NoOfConfigTasks'])
                self.assertEqual(1, metrics['NoOfItemRemovalTasks'])
