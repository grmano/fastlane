from flask import current_app
from rq import get_current_job

from easyq.api.rqb import rq
from easyq.models.job import Job
from easyq.models.task import Task


@rq.job('tasks', timeout=-1)
def add_task(task_id):
    app = current_app
    task = Task.get_by_task_id(task_id)

    job_id = get_current_job().id
    task.create_job(job_id)

    app.job_queue.enqueue(run_job, task_id, job_id, timeout=-1)

    return True


@rq.job('jobs', timeout=-1)
def run_job(task_id, job_id):
    app = current_app
    task = Task.get_by_task_id(task_id)
    job = task.get_job_by_job_id(job_id)
    logger = app.logger.bind(task_id=task_id, job_id=job_id)

    if job is None:
        return False

    image = job.image
    tag = 'latest'

    if ':' in image:
        image, tag = image.split(':')

    logger = logger.bind(image=image, tag=tag)

    logger.debug('Changing job status...', status=Job.Status.pulling)
    job.status = Job.Status.pulling
    task.save()
    logger.debug('Job status changed successfully.', status=Job.Status.pulling)

    logger.info('Downloading updated container image...', image=image, tag=tag)
    app.executor.pull(image, tag)
    logger.info('Image downloaded successfully.', image=image, tag=tag)

    logger.info('Running command in container...')
    container_id = app.executor.run(image, tag, job.command)
    logger.info(
        'Container started successfully.',
        image=image,
        tag=tag,
        container_id=container_id)

    logger.debug('Changing job status...', status=Job.Status.running)
    job.container_id = container_id
    job.status = Job.Status.running
    task.save()
    logger.debug('Job status changed successfully.', status=Job.Status.running)

    return True