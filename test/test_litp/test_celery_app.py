import unittest

from mock import patch, Mock, call
from litp.core.worker.celery_app import FatTask, configure_worker

class MockContext(object):

    def __enter__(self):
        pass

    def __exit__(self, *args):
        pass


class TestCeleryApp(unittest.TestCase):

    @patch('litp.core.worker.celery_app.threadlocal_scope_context', Mock(return_value=MockContext()))
    @patch('litp.core.worker.celery_app.engine_context', Mock(return_value=MockContext()))
    @patch('litp.core.worker.celery_app._BaseLitpTask._get_worker_context')
    @patch('litp.core.worker.celery_app.CeleryTask.__call__')
    def test_task(self, mock_celery_task_call, mock_get_context):
        mock_get_context = MockContext()
        # TORF-150204: Error handling for raised exceptions during celery tasks
        def fail_task(*args):
            raise TypeError('Celery Task Error')
        mock_celery_task_call.side_effect = fail_task
        task = FatTask()
        # Call mocked celery task
        result = task()
        self.assertEquals(result, {'error': 'Celery Task Error'})

    @patch('litp.core.worker.celery_app.cherrypy.config.update', Mock())
    @patch('litp.core.worker.celery_app.PluginManager', Mock())
    @patch('litp.core.worker.celery_app.init_metrics', Mock())
    def test_force_debug(self):
        # TORF-161280: force_debug() is called with correct arguments and sets
        # log level as expected.
        mock_engine = Mock()

        # Logging item has force_debug='true', force_debug parameter is True
        with patch('litp.core.worker.celery_app.DataManager') as MockDataManager:
            data_manager_instance = MockDataManager.return_value
            data_manager_instance.model.get.return_value = Mock(force_debug='true')
            with patch('litp.core.worker.celery_app.ModelManager.force_debug') as mock_force:
                configure_worker(mock_engine)
                self.assertTrue(data_manager_instance.commit.called)
                self.assertTrue(data_manager_instance.close.called)
                expected = [call(force_debug=True, normal_start=False)]
                self.assertEqual(expected, mock_force.call_args_list)


        # Logging item has force_debug='false', force_debug parameter is False
        with patch('litp.core.worker.celery_app.DataManager') as MockDataManager:
            data_manager_instance = MockDataManager.return_value
            data_manager_instance.model.get.return_value = Mock(force_debug='false')
            with patch('litp.core.worker.celery_app.ModelManager.force_debug') as mock_force:
                configure_worker(mock_engine)
                self.assertTrue(data_manager_instance.commit.called)
                self.assertTrue(data_manager_instance.close.called)
                expected = [call(force_debug=False, normal_start=False)]
                self.assertEqual(expected, mock_force.call_args_list)
