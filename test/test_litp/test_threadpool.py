import json
import unittest
import time
from litp.core.litp_threadpool import create_job, get_job, add_job
from litp.core.litp_threadpool import current_jobs, shutdown, start
from litp.core.litp_threadpool import _set_mock
from litp.core.litp_threadpool import Job, LitpThreadPool
from threading import RLock

class BoxedCounter(object):
    def __init__(self,value):
        self.ticketLock = RLock()
        self.ticketCount = value

    def decr(self,*args,**kwargs):
        self.ticketLock.acquire(True)
        self.ticketCount += 1
        self.ticketLock.release()

    def getValue(self):
        self.ticketLock.acquire(True)
        value = self.ticketCount
        self.ticketLock.release()
        return value


def run_job(x, job):
    job.run()


class ThreadPoolTest(unittest.TestCase):
    def setUp(self):
        self.counter = BoxedCounter(0)
        self._orig_run_job = LitpThreadPool._run_job

        LitpThreadPool._run_job = run_job

    def tearDown(self):
        LitpThreadPool._run_job = self._orig_run_job

    def testAddCustomJob(self):
        for i in range(3):
            objJob = Job(object(),self.counter.decr,{},{})
            add_job( objJob )
        time.sleep(0.1)
        if self.counter.getValue() != 3:
            time.sleep(1)
        self.assertEquals(self.counter.getValue(),3 )

    def testThreadPool(self):
        def run(*args,**kwargs):
            kwargs['counter'].decr()
            return 42
        for i in range(5):
            idJob = create_job(run, counter=self.counter)
            get_job(idJob)
        time.sleep(0.1)
        if self.counter.getValue() != 5:
            time.sleep(1)
        self.assertEquals( self.counter.getValue(),5 )

    def testThreadPoolListAllJobs(self):
        pool = LitpThreadPool()
        pool.current_active_jobs()

    def testThreadPoolJobThrowsException(self):
        def suicidal():
            sleep(0.1)
            raise Exception("YES")
            return 666
        start()
        create_job(suicidal)
        time.sleep(0.2)
        shutdown()
        self.assertRaises(Exception,create_job,suicidal)

    def testThreadPoolGetJobWithBadId(self):
        pool = LitpThreadPool()
        self.assertEquals(
            pool.get_job("nonesuch"),None,
            msg="Got job object passing invalid job id"
            )

    def testThreadPoolTestMock(self):
        _set_mock()
