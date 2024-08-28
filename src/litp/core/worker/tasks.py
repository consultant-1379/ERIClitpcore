import cherrypy

from litp.core.worker.celery_app import LeanTask, FatTask
from litp.core.worker.celery_app import celery_app


@celery_app.task(bind=True, base=FatTask)
def run_plan_phase(self, phase_id):
    execution_manager = cherrypy.config["execution_manager"]
    return execution_manager.worker_run_plan_phase(phase_id)


@celery_app.task(bind=True, base=FatTask)
def run_plan(self):
    execution_manager = cherrypy.config["execution_manager"]
    return execution_manager.run_plan(celery_request_id=self.request.id)


@celery_app.task(bind=True, base=LeanTask)
def monitor_plan(self):
    execution_manager = cherrypy.config["execution_manager"]
    return execution_manager.monitor_plan()
