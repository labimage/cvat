
# Copyright (C) 2018 Intel Corporation
#
# SPDX-License-Identifier: MIT

import os
import json
import traceback
from ast import literal_eval
import shutil

from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.conf import settings
from rules.contrib.views import permission_required, objectgetter
from django.views.decorators.gzip import gzip_page
from sendfile import sendfile
from rest_framework import generics
from rest_framework.decorators import api_view, APIView
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.renderers import JSONRenderer
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework import mixins
import django_rq


from . import annotation, task, models
from cvat.settings.base import JS_3RDPARTY, CSS_3RDPARTY
from cvat.apps.authentication.decorators import login_required
from requests.exceptions import RequestException
import logging
from .log import slogger, clogger
from cvat.apps.engine.models import StatusChoice, Task, Job, Plugin
from cvat.apps.engine.serializers import (TaskSerializer, UserSerializer,
   ExceptionSerializer, AboutSerializer, JobSerializer, ImageMetaSerializer,
   RqStatusSerializer, TaskDataSerializer, PluginSerializer)
from django.contrib.auth.models import User
from cvat.apps.authentication import auth
from rest_framework.permissions import SAFE_METHODS

# Server REST API

class ServerViewSet(viewsets.ViewSet):
    serializer_class = None

    # To get nice documentation about ServerViewSet actions it is necessary
    # to implement the method. By default, ViewSet doesn't provide it.
    def get_serializer(self, *args, **kwargs):
        return self.serializer_class(*args, **kwargs)

    @action(detail=False, methods=['GET'], serializer_class=AboutSerializer)
    def about(self, request):
        from cvat import __version__ as cvat_version
        about = {
            "name": "Computer Vision Annotation Tool",
            "version": cvat_version,
            "description": "CVAT is completely re-designed and re-implemented " +
                "version of Video Annotation Tool from Irvine, California " +
                "tool. It is free, online, interactive video and image annotation " +
                "tool for computer vision. It is being used by our team to " +
                "annotate million of objects with different properties. Many UI " +
                "and UX decisions are based on feedbacks from professional data " +
                "annotation team."
        }
        serializer = AboutSerializer(data=about)
        if serializer.is_valid(raise_exception=True):
            return Response(data=serializer.data)

    @action(detail=False, methods=['POST'], serializer_class=ExceptionSerializer)
    def exception(self, request):
        serializer = ExceptionSerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            message = JSONRenderer().render(serializer.data)
            jid = serializer.data["job"]
            tid = serializer.data["task"]
            if jid:
                clogger.job[jid].error(message)
            elif tid:
                clogger.task[tid].error(message)
            else:
                clogger.glob.error(message)

            return Response(serializer.data, status=status.HTTP_201_CREATED)

    # @action(detail=False, methods=['GET'], serializer_class=ShareSerializer)
    # def share(self, request):
    #     serializer = ShareSerializer(data=request.data)
    #     if serializer.is_valid(raise_exception=True):
    #         return Response(serializer.data)


class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.all()
    serializer_class = TaskSerializer

    def get_permissions(self):
        http_method = self.request.method
        permissions = [auth.IsAuthenticated]

        if http_method in auth.SAFE_METHODS:
            permissions.append(auth.TaskAccessPermission)
        elif http_method in ["POST"]:
            permissions.append(auth.TaskCreatePermission)
        elif http_method in ["PATCH", "PUT"]:
            permissions.append(auth.TaskChangePermission)
        elif http_method in ["DELETE"]:
            permissions.append(auth.TaskDeletePermission)
        else:
            permissions.append(auth.AdminRolePermission)

        return [perm() for perm in permissions]

    def perform_create(self, serializer):
        if self.request.data.get('owner', None):
            serializer.save()
        else:
            serializer.save(owner=self.request.user)

    def perform_destroy(self, instance):
        task_dirname = instance.get_task_dirname()
        super().perform_destroy(instance)
        shutil.rmtree(task_dirname, ignore_errors=True)

    @action(detail=True, methods=['GET'], serializer_class=JobSerializer)
    def jobs(self, request, pk):
        queryset = Job.objects.filter(segment__task_id=pk)
        serializer = JobSerializer(queryset, many=True,
            context={"request": request})

        return Response(serializer.data)

    @action(detail=True, methods=['PUT'], serializer_class=TaskDataSerializer)
    def data(self, request, pk):
        db_task = self.get_object()
        serializer = TaskDataSerializer(db_task, data=request.data)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)

    #@action(detail=True, methods=['GET', 'DELETE', 'POST'], serializer_class=None)
    @action(detail=True, methods=['GET'], serializer_class=None)
    def annotations(self, request, pk):
        pass

    @action(detail=True, methods=['GET'], serializer_class=RqStatusSerializer)
    def status(self, request, pk):
        response = self._get_rq_response(queue="default",
            job_id="/api/{}/tasks/{}".format(request.version, pk))
        serializer = RqStatusSerializer(data=response)

        if serializer.is_valid(raise_exception=True):
            return Response(serializer.data)

    def _get_rq_response(self, queue, job_id):
        queue = django_rq.get_queue(queue)
        job = queue.fetch_job(job_id)
        response = {}
        if job is None or job.is_finished:
            response = { "state": "Finished" }
        elif job.is_queued:
            response = { "state": "Queued" }
        elif job.is_failed:
            response = { "state": "Failed", "message": job.exc_info }
        else:
            response = { "state": "Started" }
            if 'status' in job.meta:
                response['message'] = job.meta['status']

        return response

    @action(detail=True, methods=['GET'], serializer_class=ImageMetaSerializer,
        url_path='frames/meta')
    def data_info(self, request, pk):
        try:
            db_task = models.Task.objects.get(pk=pk)
            meta_cache_file = open(db_task.get_image_meta_cache_path())
        except OSError:
            task.make_image_meta_cache(db_task)
            meta_cache_file = open(db_task.get_image_meta_cache_path())

        data = literal_eval(meta_cache_file.read())
        serializer = ImageMetaSerializer(many=True, data=data['original_size'])
        if serializer.is_valid(raise_exception=True):
            return Response(serializer.data)

    @action(detail=True, methods=['GET'], serializer_class=None,
        url_path='frames/(?P<frame>\d+)')
    def frame(self, request, pk, frame):
        """Get a frame for the task"""

        try:
            # Follow symbol links if the frame is a link on a real image otherwise
            # mimetype detection inside sendfile will work incorrectly.
            path = os.path.realpath(task.get_frame_path(pk, frame))
            return sendfile(request, path)
        except Exception as e:
            slogger.task[pk].error(
                "cannot get frame #{}".format(frame), exc_info=True)
            return HttpResponseBadRequest(str(e))


class JobViewSet(viewsets.GenericViewSet,
    mixins.RetrieveModelMixin, mixins.UpdateModelMixin):
    queryset = Job.objects.all()
    serializer_class = JobSerializer

    def get_permissions(self):
        http_method = self.request.method
        permissions = [auth.IsAuthenticated]

        if http_method in SAFE_METHODS:
            permissions.append(auth.JobAccessPermission)
        elif http_method in ["PATCH", "PUT"]:
            permissions.append(auth.JobChangePermission)
        else:
            permissions.append(auth.AdminRolePermission)

        return [perm() for perm in permissions]

    #@action(detail=True, methods=['GET', 'DELETE', 'POST'], serializer_class=None)
    @action(detail=True, methods=['GET'], serializer_class=None)
    def annotations(self, request, pk):
        pass


class UserViewSet(viewsets.GenericViewSet, mixins.ListModelMixin,
    mixins.RetrieveModelMixin, mixins.UpdateModelMixin):
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def get_permissions(self):
        http_method = self.request.method
        permissions = [auth.IsAuthenticated]

        if self.action in ["self"]:
            pass
        else:
            permissions.append(auth.AdminRolePermission)

        return [perm() for perm in permissions]

    @action(detail=False, methods=['GET'], serializer_class=UserSerializer)
    def self(self, request):
        serializer = UserSerializer(request.user, context={ "request": request })
        return Response(serializer.data)

class PluginViewSet(viewsets.ModelViewSet):
    queryset = Plugin.objects.all()
    serializer_class = PluginSerializer

    # @action(detail=True, methods=['GET', 'PATCH', 'PUT'], serializer_class=None)
    # def config(self, request, name):
    #     pass

    # @action(detail=True, methods=['GET', 'POST'], serializer_class=None)
    # def data(self, request, name):
    #     pass

    # @action(detail=True, methods=['GET', 'DELETE', 'PATCH', 'PUT'],
    #     serializer_class=None, url_path='data/(?P<id>\d+)')
    # def data_detail(self, request, name, id):
    #     pass


    @action(detail=True, methods=['GET', 'POST'], serializer_class=RqStatusSerializer)
    def requests(self, request, name):
        pass

    @action(detail=True, methods=['GET', 'DELETE'],
        serializer_class=RqStatusSerializer, url_path='requests/(?P<id>\d+)')
    def request_detail(self, request, name, id):
        pass



# XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
# High Level server API


@login_required
@permission_required(perm=['engine.job.access'],
                     fn=objectgetter(models.Job, 'jid'), raise_exception=True)
def catch_client_exception(request, jid):
    data = json.loads(request.body.decode('utf-8'))
    for event in data['exceptions']:
        clogger.job[jid].error(json.dumps(event))

    return HttpResponse()


@login_required
def dispatch_request(request):
    """An entry point to dispatch legacy requests"""
    if request.method == 'GET' and 'id' in request.GET:
        return render(request, 'engine/annotation.html', {
            'css_3rdparty': CSS_3RDPARTY.get('engine', []),
            'js_3rdparty': JS_3RDPARTY.get('engine', []),
            'status_list': [str(i) for i in StatusChoice]
        })
    else:
        return redirect('/dashboard/')

@login_required
# @permission_required(perm=['engine.task.access'],
#    fn=objectgetter(models.Task, 'tid'), raise_exception=True)
# We have commented lines above because the objectgetter() will raise 404 error in
# cases when a task creating ends with an error. So an user don't get an actual reason of an error.
def check_task(request, tid):
    """Check the status of a task"""
    try:
        slogger.glob.info("check task #{}".format(tid))
        response = task.check(tid)
    except Exception as e:
        slogger.glob.error("cannot check task #{}".format(tid), exc_info=True)
        return HttpResponseBadRequest(str(e))

    return JsonResponse(response)


@login_required
@permission_required(perm=['engine.task.delete'],
                     fn=objectgetter(models.Task, 'tid'), raise_exception=True)
def delete_task(request, tid):
    """Delete the task"""
    try:
        slogger.glob.info("delete task #{}".format(tid))
        task.delete(tid)
    except Exception as e:
        slogger.glob.error("cannot delete task #{}".format(tid), exc_info=True)
        return HttpResponseBadRequest(str(e))

    return HttpResponse()


@login_required
@permission_required(perm=['engine.task.change'],
                     fn=objectgetter(models.Task, 'tid'), raise_exception=True)
def update_task(request, tid):
    """Update labels for the task"""
    try:
        slogger.task[tid].info("update task request")
        labels = request.POST['labels']
        task.update(tid, labels)
    except Exception as e:
        slogger.task[tid].error("cannot update task", exc_info=True)
        return HttpResponseBadRequest(str(e))

    return HttpResponse()


@login_required
@permission_required(perm=['engine.task.access'],
                     fn=objectgetter(models.Task, 'tid'), raise_exception=True)
def get_task(request, tid):
    try:
        slogger.task[tid].info("get task request")
        response = task.get(tid)
    except Exception as e:
        slogger.task[tid].error("cannot get task", exc_info=True)
        return HttpResponseBadRequest(str(e))

    return JsonResponse(response, safe=False)


@login_required
@permission_required(perm=['engine.job.access'],
                     fn=objectgetter(models.Job, 'jid'), raise_exception=True)
def get_job(request, jid):
    try:
        slogger.job[jid].info("get job #{} request".format(jid))
        response = task.get_job(jid)
    except Exception as e:
        slogger.job[jid].error("cannot get job #{}".format(jid), exc_info=True)
        return HttpResponseBadRequest(str(e))

    return JsonResponse(response, safe=False)


@login_required
@permission_required(perm=['engine.task.access'],
                     fn=objectgetter(models.Task, 'tid'), raise_exception=True)
def dump_annotation(request, tid):
    try:
        slogger.task[tid].info("dump annotation request")
        annotation.dump(tid, annotation.FORMAT_XML,
                        request.scheme, request.get_host())
    except Exception as e:
        slogger.task[tid].error("cannot dump annotation", exc_info=True)
        return HttpResponseBadRequest(str(e))

    return HttpResponse()


@login_required
@gzip_page
@permission_required(perm=['engine.task.access'],
                     fn=objectgetter(models.Task, 'tid'), raise_exception=True)
def check_annotation(request, tid):
    try:
        slogger.task[tid].info("check annotation")
        response = annotation.check(tid)
    except Exception as e:
        slogger.task[tid].error("cannot check annotation", exc_info=True)
        return HttpResponseBadRequest(str(e))

    return JsonResponse(response)


@login_required
@gzip_page
@permission_required(perm=['engine.task.access'],
                     fn=objectgetter(models.Task, 'tid'), raise_exception=True)
def download_annotation(request, tid):
    try:
        slogger.task[tid].info("get dumped annotation")
        db_task = models.Task.objects.get(pk=tid)
        response = sendfile(request, db_task.get_dump_path(), attachment=True,
                            attachment_filename='{}_{}.xml'.format(db_task.id, db_task.name))
    except Exception as e:
        slogger.task[tid].error("cannot get dumped annotation", exc_info=True)
        return HttpResponseBadRequest(str(e))

    return response


@login_required
@gzip_page
@permission_required(perm=['engine.job.access'],
                     fn=objectgetter(models.Job, 'jid'), raise_exception=True)
def get_annotation(request, jid):
    try:
        slogger.job[jid].info("get annotation for {} job".format(jid))
        response = annotation.get(jid)
    except Exception as e:
        slogger.job[jid].error(
            "cannot get annotation for job {}".format(jid), exc_info=True)
        return HttpResponseBadRequest(str(e))

    return JsonResponse(response, safe=False)


@login_required
@permission_required(perm=['engine.job.change'],
                     fn=objectgetter(models.Job, 'jid'), raise_exception=True)
def save_annotation_for_job(request, jid):
    try:
        slogger.job[jid].info("save annotation for {} job".format(jid))
        data = json.loads(request.body.decode('utf-8'))
        if 'annotation' in data:
            annotation.save_job(jid, json.loads(data['annotation']))
        if 'logs' in data:
            for event in json.loads(data['logs']):
                clogger.job[jid].info(json.dumps(event))
        slogger.job[jid].info(
            "annotation have been saved for the {} job".format(jid))
    except RequestException as e:
        slogger.job[jid].error(
            "cannot send annotation logs for job {}".format(jid), exc_info=True)
        return HttpResponseBadRequest(str(e))
    except Exception as e:
        slogger.job[jid].error(
            "cannot save annotation for job {}".format(jid), exc_info=True)
        return HttpResponseBadRequest(str(e))

    return HttpResponse()


@login_required
@permission_required(perm=['engine.task.change'],
                     fn=objectgetter(models.Task, 'tid'), raise_exception=True)
def save_annotation_for_task(request, tid):
    try:
        slogger.task[tid].info("save annotation request")
        data = json.loads(request.body.decode('utf-8'))
        annotation.save_task(tid, data)
    except Exception as e:
        slogger.task[tid].error("cannot save annotation", exc_info=True)
        return HttpResponseBadRequest(str(e))

    return HttpResponse()


@login_required
@permission_required(perm=['engine.task.change'],
                     fn=objectgetter(models.Task, 'tid'), raise_exception=True)
def delete_annotation_for_task(request, tid):
    try:
        slogger.task[tid].info("delete annotation request")
        annotation.clear_task(tid)
    except Exception as e:
        slogger.task[tid].error("cannot delete annotation", exc_info=True)
        return HttpResponseBadRequest(str(e))

    return HttpResponse()


@login_required
@permission_required(perm=['engine.job.change'],
                     fn=objectgetter(models.Job, 'jid'), raise_exception=True)
def save_job_status(request, jid):
    try:
        data = json.loads(request.body.decode('utf-8'))
        status = data['status']
        slogger.job[jid].info("changing job status request")
        task.save_job_status(jid, status, request.user.username)
    except Exception as e:
        if jid:
            slogger.job[jid].error("cannot change status", exc_info=True)
        else:
            slogger.glob.error("cannot change status", exc_info=True)
        return HttpResponseBadRequest(str(e))
    return HttpResponse()


@login_required
def get_username(request):
    response = {'username': request.user.username}
    return JsonResponse(response, safe=False)


def rq_handler(job, exc_type, exc_value, tb):
    job.exc_info = "".join(
        traceback.format_exception_only(exc_type, exc_value))
    job.save()
    module = job.id.split('.')[0]
    if module == 'task':
        return task.rq_handler(job, exc_type, exc_value, tb)
    elif module == 'annotation':
        return annotation.rq_handler(job, exc_type, exc_value, tb)

    return True
