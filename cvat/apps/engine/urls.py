
# Copyright (C) 2018 Intel Corporation
#
# SPDX-License-Identifier: MIT

from django.urls import path, include
from . import views
from rest_framework import routers
from rest_framework.documentation import include_docs_urls

router = routers.DefaultRouter(trailing_slash=False)
router.register('tasks', views.TaskViewSet)
router.register('jobs', views.JobViewSet)
router.register('users', views.UserViewSet)
router.register('server', views.ServerViewSet, basename='server')
router.register('plugins', views.PluginViewSet)

urlpatterns = [
    # documentation for API
    path('api/docs/', include_docs_urls(title='CVAT REST API', public=True)),
    # entry point for API
    path('api/v1/', include((router.urls, 'cvat'), namespace='v1')),


    # deprecated API
    path('', views.dispatch_request),
    #path('create/task', views.create_task),
    #path('get/task/<int:tid>/frame/<int:frame>', views.get_frame),
    path('check/task/<int:tid>', views.check_task),
    path('delete/task/<int:tid>', views.delete_task),
    path('update/task/<int:tid>', views.update_task),
    path('get/job/<int:jid>', views.get_job),
    path('get/task/<int:tid>', views.get_task),
    path('dump/annotation/task/<int:tid>', views.dump_annotation),
    path('check/annotation/task/<int:tid>', views.check_annotation),
    path('download/annotation/task/<int:tid>', views.download_annotation),
    path('save/annotation/job/<int:jid>', views.save_annotation_for_job),
    path('save/annotation/task/<int:tid>', views.save_annotation_for_task),
    path('delete/annotation/task/<int:tid>', views.delete_annotation_for_task),
    path('get/annotation/job/<int:jid>', views.get_annotation),
    path('get/username', views.get_username),
    path('save/exception/<int:jid>', views.catch_client_exception),
    path('save/status/job/<int:jid>', views.save_job_status),
]
