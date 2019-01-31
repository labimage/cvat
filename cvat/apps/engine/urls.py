
# Copyright (C) 2018 Intel Corporation
#
# SPDX-License-Identifier: MIT

from django.urls import path
from . import views

REST_API_PREFIX = 'api/<version>/'

urlpatterns = [
    # entry point for API
    path(REST_API_PREFIX, views.api_root, name='root'),
    # GET list of users, POST a new user
    path(REST_API_PREFIX + 'users/', views.UserList.as_view(),
        name='user-list'),
    # GET current active user
    path(REST_API_PREFIX + 'users/self', views.UserSelf.as_view(),
        name='user-self'),
    # GET, DELETE, PATCH the user
    path(REST_API_PREFIX + 'users/<int:pk>', views.UserDetail.as_view(),
        name='user-detail'),
    # GET a frame for a specific task
    path(REST_API_PREFIX + 'tasks/<int:pk>/frames/<int:frame>',
        views.get_frame, name='task-frame'),
    # POST an exception
    path(REST_API_PREFIX + 'exceptions/', views.ClientException.as_view(),
        name='exception-list'),
    # GET information about the backend
    path(REST_API_PREFIX + 'about/', views.About.as_view(), name='about'),
    # GET a list of jobs for a specific task
    path(REST_API_PREFIX + 'tasks/<int:pk>/jobs/', views.JobList.as_view(),
        name='job-list'),
    # GET and PATCH the specific job
    path(REST_API_PREFIX + 'jobs/<int:pk>', views.JobDetail.as_view(),
        name='job-detail'),
    # GET a list of annotation tasks, POST an annotation task
    path(REST_API_PREFIX + 'tasks/', views.TaskList.as_view(),
        name='task-list'),
    path( # GET, DELETE, PATCH
        REST_API_PREFIX + 'tasks/<int:pk>', views.TaskDetail.as_view(),
        name='task-detail'),
    path( # GET
        REST_API_PREFIX + 'tasks/<int:pk>/status', views.TaskStatus.as_view(),
        name='task-status'),
    # GET meta information for all frames
    path(REST_API_PREFIX + 'tasks/<int:pk>/frames/meta',
        views.get_image_meta_cache, name='image-meta-cache'),



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
