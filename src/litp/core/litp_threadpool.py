##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################


from collections import deque
from functools import wraps
from Queue import Queue

import threading
import time
import uuid

from litp.core.scope_utils import threadlocal_scope
from litp.core.litp_logging import LitpLogger
log = LitpLogger()

_FIVE_MINS = 5 * 60


# FIXME: In longer term, avoid using Singleton pattern as well..
class ThreadPoolSingleton(object):
    __threadpool = None
    __mocked = False

    @classmethod
    def get(cls):
        if not cls.__threadpool:
            cls.__threadpool = LitpThreadPool()
            cls.__threadpool.start()
        return cls.__threadpool

    @classmethod
    def set_mock(cls, mock=True):
        cls.__mocked = mock

    @classmethod
    def get_mock(cls):
        return cls.__mocked


def _get_threadpool():
    """ Threadpool is used as a singleton. This function lazy-initialises the
        threadpool as appropriate
    """
    return ThreadPoolSingleton().get()


def create_job(func, *args, **kwargs):
    """ Helper function to start a background job
        :param func: The function or method being scheduled
        :type func: Function
        :param args: Arguments for the scheduled call
        :type args: list
        :param kwargs: Keyword arguments for the scheduled call
        :type kwargs: list
        :returns: Job id for the created job
        :rtype: string
    """
    return _get_threadpool().create_job(func, *args, **kwargs)


def get_job(jobid):
    """ Helper function to get a job
    """
    return _get_threadpool().get_job(jobid)


def add_job(job):
    """ Helper function to add a custom job
    """
    return _get_threadpool().add_job(job)


def current_jobs():
    return _get_threadpool().current_jobs()


def shutdown():
    """ Helper function which stops the singleton thread pool
    """
    _get_threadpool().stop_wait()


def start():
    """ Helper function which starts the threadpool
    """
    _get_threadpool().start()


class Job(object):
    """ Class representing a single background job on the queue
    """
    def __init__(self, cls, method, args, kwargs):
        self._jobid = str(uuid.uuid1())
        self._cls = cls
        self._method = method
        self._args = args
        self._kwargs = kwargs
        self.result = None
        self.processing = True
        self.finished_time = 0
        self.executed_tasks = []

    def __repr__(self):
        return "Job(%s, %s) = %s" % (self._method, self._args, self.result)

    def run(self):
        if not self.processing:
            log.trace.debug("Job %s not executing", self._jobid)
            return
        try:
            log.trace.debug("Starting background call to %s(%s, %s)",
                self._method.__name__, self._args, self._kwargs)
            self.result = self._method(self._cls, self, *self._args,
                **self._kwargs)
                                 # we need to catch all exceptions here
        except Exception as ex:  # pylint: disable=W0703
            log.trace.exception("Exception running background job")
            self.result = dict(
                error="Exception running background job: %s" % (ex,))
        finally:
            self.processing = False
            log.trace.debug("Ending background call to %s(%s, %s)",
                self._method.__name__, self._args, self._kwargs)

    def stop(self):
        self.processing = False

    def external(self):
        return dict(vpath=self._cls.get_vpath(),
                    command=self._method.__name__,
                    result=self.result,
                    jobid=self._jobid,
                    etasks=self.executed_tasks)


def background(method):
    ''' Background decorator. Applying this decorator to a method will
        run the method as a background job. i.e.

        @background
        def call(self, job, *args, **kwargs):
            ...

        The extra parameter, job, is passed to the method.
        Note: this decorator is written specifically for methods of objects
            which subclass the LitpItem class.
    '''
    @wraps(method)
    def call(cls, *args, **kwargs):
        job = Job(cls, method, args, kwargs)
        pool = ThreadPoolSingleton()
        if pool.get_mock() or \
            threading.currentThread().getName() == "JobThread":
            retval = method(cls, job, *args, **kwargs)
            retval.update({'jobid': '0'})
            return retval
        jobid = add_job(job)
        return {'success': {'jobid': jobid}}
    call.exposed = True
    call.background = True
    return call


def _set_mock(mock=True):
    ''' Mocking this decorator is the easiest way to pass these tests
    '''
    ThreadPoolSingleton().set_mock(mock)


class LitpThreadPool(object):
    """ Threadpool implementation. Waits for calls to start jobs before
        starting threads. Queues up jobs over the max thread limit
    """
    def __init__(self, max_threads=2):
        """
        Defines a LitpThreadPool
        :param max_threads: Maximum number of concurrent threads
        :type max_threads: Integer
        """
        self._queue = Queue()
        self._running = False
        self._max_threads = max_threads
        self._processing = deque()

    def start(self):
        """ Start processing requests for the threadpool
        """
        self._running = True
        for _ in range(self._max_threads):
            thread = threading.Thread(None, self._run, "JobThread")
            thread.daemon = True
            thread.start()

    def _run(self):
        while True:
            self._process_queue_item()
        log.trace.debug("Falling out of thread")

    def _process_queue_item(self):
        job = self._queue.get()
        self._processing.append(job)
        self._run_job(job)
        job.finished_time = self._get_now()
        self._queue.task_done()
        self._clean_old_jobs()

    @threadlocal_scope
    def _run_job(self, job):
        job.run()

    def _clean_old_jobs(self):
        for job in list(self._processing):
            if not job.processing and job.finished_time + _FIVE_MINS < \
                    self._get_now():
                self._processing.remove(job)

    def stop(self):
        """ Stop the threadpool from processing requests
        """
        self._running = False
        all_jobs = list(self._queue.queue) + list(self._processing)
        for job in all_jobs:
            job.stop()
        log.trace.info("LitpThreadPool : stopped")

    def _get_now(self):
        return time.time()

    def create_job(self, func, *args, **kwargs):
        """ Process the given function or method in the pool,
            saving the result when complete. Arguments and
            keyword arguments are passed through.
            :param func: The function or method being scheduled
            :type func: function
            :param args: Arguments for the scheduled call
            :type args: list
            :param kwargs: Keyword arguments for the scheduled call
            :type kwargs: list
            :returns: Job id for the created job
            :rtype: string
        """
        return self.add_job(Job(object(), func, args, kwargs))

    def add_job(self, job):
        """ Add a job instance to the process queue.
            Write your own subclass of the Job class and call this instead of
            using a call to create_job()
            :param job: Job object to be added to the pool
            :type job: Job
            :returns: Job id for the created job
            :rtype: string
        """
        if not self._running:
            raise Exception("Threadpool shutting down, cannot start job")
        self._queue.put(job)
        return job._jobid

    def get_job(self, jobid):
        """ Get job with given jobid from any of the various queues
            :param jobid: Job id to get from the pool
            :type jobid: string
            :returns: The job object or None if not found
            :rtype: Job object or None
        """
        all_jobs = list(self._queue.queue) + list(self._processing)
        for job in all_jobs:
            if job._jobid == jobid:
                return job
        return None

    def stop_wait(self):
        """ Stop the threadpool from processing, and waits for all running
            threads to complete
        """
        self.stop()
        self.wait()

    def wait(self):
        """ Waits for all current background jobs to finish
        """
        log.trace.info("LitpThreadPool : waiting for jobs to finish")
        self._queue.join()

    def current_jobs(self):
        """ Returns a list of all jobs in this pool
        """
        return list(self._processing) + list(self._queue.queue)

    def current_active_jobs(self):
        """ Returns a list of active jobs in this pool
        """
        return [job for job in self.current_jobs() if job.processing]
