
# Copyright (C) 2018 Intel Corporation
#
# SPDX-License-Identifier: MIT

from django.urls import path, include
from . import views
from rest_framework import routers
from rest_framework.documentation import include_docs_urls

REST_API_PREFIX = 'api/<version>/'

router = routers.DefaultRouter(trailing_slash=False)
router.register('tasks', views.TaskViewSet)
router.register('jobs', views.JobViewSet)
router.register('users', views.UserViewSet)
router.register('', views.ServerViewSet, basename='server')

urlpatterns = [
    # documentation for API
    path('api/docs/', include_docs_urls(title='CVAT REST API')),
    # entry point for API
    path(REST_API_PREFIX, include(router.urls)),
    path( # PUT
        REST_API_PREFIX + 'tasks/<int:pk>/data', views.dummy_view,
        name='task-data'),

    path( # GET, DELETE, PATCH, PUT
        REST_API_PREFIX + 'tasks/<int:pk>/annotations/',
        views.dummy_view,
        name='task-annotations'),
    path( # GET, DELETE, PATCH, PUT
        REST_API_PREFIX + 'jobs/<int:pk>/annotations/',
        views.dummy_view,
        name='job-annotations'),
    path( # GET
        REST_API_PREFIX + 'plugins/',
        views.dummy_view,
        name='plugin-list'),
    path( # GET, PATCH, PUT
        REST_API_PREFIX + 'plugins/<slug:name>/config/',
        views.dummy_view,
        name='plugin-config'),
    path( # GET, POST
        REST_API_PREFIX + 'plugins/<slug:name>/data/',
        views.dummy_view,
        name='plugin-data-list'),
    path( # GET, PATCH, DELETE, PUT
        REST_API_PREFIX + 'plugins/<slug:name>/data/<int:id>',
        views.dummy_view,
        name='plugin-data-detail'),
    path( # GET, POST
        REST_API_PREFIX + 'plugins/<slug:name>/requests/',
        views.dummy_view,
        name='plugin-request-list'),
    path( # GET, DELETE
        REST_API_PREFIX + 'plugins/<slug:name>/requests/<int:id>',
        views.dummy_view,
        name='plugin-request-detail'),

    path('delete/task/<int:tid>', views.delete_task), ####
    path('update/task/<int:tid>', views.update_task), ####
    path('dump/annotation/task/<int:tid>', views.dump_annotation), ###
    path('check/annotation/task/<int:tid>', views.check_annotation), ###
    path('download/annotation/task/<int:tid>', views.download_annotation), ###
    path('save/annotation/job/<int:jid>', views.save_annotation_for_job), ###
    path('save/annotation/task/<int:tid>', views.save_annotation_for_task), ###
    path('delete/annotation/task/<int:tid>', views.delete_annotation_for_task), ###
    path('get/annotation/job/<int:jid>', views.get_annotation), ###
    path('save/exception/<int:jid>', views.catch_client_exception), ###

    path('', views.dispatch_request),
]
