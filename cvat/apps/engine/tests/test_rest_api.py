# Copyright (C) 2018 Intel Corporation
#
# SPDX-License-Identifier: MIT

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.contrib.auth.models import User, Group
from cvat.apps.engine.models import Task, Segment, Job, StatusChoice

def setUpModule():
    import logging
    global django_request_logger
    global django_request_loglevel

    django_request_logger = logging.getLogger('django.request')
    django_request_loglevel = django_request_logger.getEffectiveLevel()
    django_request_logger.setLevel(logging.ERROR)

def tearDownModule():
    django_request_logger.setLevel(django_request_loglevel)


def createUsers(cls):
    (group_admin, _) = Group.objects.get_or_create(name="admin")
    (group_user, _) = Group.objects.get_or_create(name="user")
    (group_annotator, _) = Group.objects.get_or_create(name="annotator")
    (group_observer, _) = Group.objects.get_or_create(name="observer")

    user_admin = User.objects.create_superuser(username="admin", email="",
        password="admin")
    user_admin.groups.add(group_admin)
    user_owner = User.objects.create_user(username="user1", password="user1")
    user_owner.groups.add(group_user)
    user_assignee = User.objects.create_user(username="user2", password="user2")
    user_assignee.groups.add(group_annotator)
    user_annotator = User.objects.create_user(username="user3", password="user3")
    user_annotator.groups.add(group_annotator)
    user_observer = User.objects.create_user(username="user4", password="user4")
    user_observer.groups.add(group_observer)
    user_dummy = User.objects.create_user(username="user5", password="user5")
    user_dummy.groups.add(group_user)

    cls.admin = user_admin
    cls.owner = user_owner
    cls.assignee = user_assignee
    cls.annotator = user_annotator
    cls.observer = user_observer
    cls.user = user_dummy

def createTask(cls):
    task = {
        "name": "my test task",
        "owner": cls.owner,
        "assignee": cls.assignee,
        "overlap": 0,
        "segment_size": 100,
        "z_order": False,
        "image_quality": 75,
        "size": 100
    }
    cls.task = Task.objects.create(**task)

    segment = {
        "start_frame": 0,
        "stop_frame": 100
    }
    cls.segment = Segment.objects.create(task=cls.task, **segment)
    cls.job = Job.objects.create(segment=cls.segment, assignee=cls.annotator)


class JobGetAPITestCase(APITestCase):
    def setUp(self):
        self.client = APIClient()

    @classmethod
    def setUpTestData(cls):
        createUsers(cls)
        createTask(cls)

    def _run_api_v1_jobs_id(self, jid, user):
        if user:
            self.client.force_login(user, backend='django.contrib.auth.backends.ModelBackend')

        response = self.client.get('/api/v1/jobs/{}'.format(jid))

        if user:
            self.client.logout()

        return response

    def _check_request(self, response):
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.job.id)
        self.assertEqual(response.data["status"], StatusChoice.ANNOTATION)
        self.assertEqual(response.data["start_frame"], self.job.segment.start_frame)
        self.assertEqual(response.data["stop_frame"], self.job.segment.stop_frame)

    def test_api_v1_jobs_id_admin(self):
        response = self._run_api_v1_jobs_id(self.job.id, self.admin)
        self._check_request(response)
        response = self._run_api_v1_jobs_id(self.job.id + 10, self.admin)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_api_v1_jobs_id_owner(self):
        response = self._run_api_v1_jobs_id(self.job.id, self.owner)
        self._check_request(response)
        response = self._run_api_v1_jobs_id(self.job.id + 10, self.owner)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_api_v1_jobs_id_annotator(self):
        response = self._run_api_v1_jobs_id(self.job.id, self.annotator)
        self._check_request(response)
        response = self._run_api_v1_jobs_id(self.job.id + 10, self.annotator)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_api_v1_jobs_id_observer(self):
        response = self._run_api_v1_jobs_id(self.job.id, self.observer)
        self._check_request(response)
        response = self._run_api_v1_jobs_id(self.job.id + 10, self.observer)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_api_v1_jobs_id_user(self):
        response = self._run_api_v1_jobs_id(self.job.id, self.user)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        response = self._run_api_v1_jobs_id(self.job.id + 10, self.user)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_api_v1_jobs_id_no_auth(self):
        response = self._run_api_v1_jobs_id(self.job.id, None)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        response = self._run_api_v1_jobs_id(self.job.id + 10, None)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class JobUpdateAPITestCase(APITestCase):
    def setUp(self):
        self.client = APIClient()
        createTask(self)

    @classmethod
    def setUpTestData(cls):
        createUsers(cls)

    def _run_api_v1_jobs_id(self, jid, user, data):
        if user:
            self.client.force_login(user, backend='django.contrib.auth.backends.ModelBackend')

        response = self.client.put('/api/v1/jobs/{}'.format(jid), data=data, format='json')

        if user:
            self.client.logout()

        return response

    def _check_request(self, response, data):
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.job.id)
        self.assertEqual(response.data["status"], data.get('status', self.job.status))
        self.assertEqual(response.data["assignee"], data.get('assignee', self.job.assignee.id))
        self.assertEqual(response.data["start_frame"], self.job.segment.start_frame)
        self.assertEqual(response.data["stop_frame"], self.job.segment.stop_frame)

    def test_api_v1_jobs_id_admin(self):
        data = {"status": StatusChoice.COMPLETED, "assignee": self.owner.id}
        response = self._run_api_v1_jobs_id(self.job.id, self.admin, data)
        self._check_request(response, data)
        response = self._run_api_v1_jobs_id(self.job.id + 10, self.admin, data)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_api_v1_jobs_id_owner(self):
        data = {"status": StatusChoice.VALIDATION, "assignee": self.annotator.id}
        response = self._run_api_v1_jobs_id(self.job.id, self.owner, data)
        self._check_request(response, data)
        response = self._run_api_v1_jobs_id(self.job.id + 10, self.owner, data)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_api_v1_jobs_id_annotator(self):
        data = {"status": StatusChoice.ANNOTATION, "assignee": self.user.id}
        response = self._run_api_v1_jobs_id(self.job.id, self.annotator, data)
        self._check_request(response, data)
        response = self._run_api_v1_jobs_id(self.job.id + 10, self.annotator, data)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_api_v1_jobs_id_observer(self):
        data = {"status": StatusChoice.ANNOTATION, "assignee": self.admin.id}
        response = self._run_api_v1_jobs_id(self.job.id, self.observer, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        response = self._run_api_v1_jobs_id(self.job.id + 10, self.observer, data)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_api_v1_jobs_id_user(self):
        data = {"status": StatusChoice.ANNOTATION, "assignee": self.user.id}
        response = self._run_api_v1_jobs_id(self.job.id, self.user, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        response = self._run_api_v1_jobs_id(self.job.id + 10, self.user, data)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_api_v1_jobs_id_no_auth(self):
        data = {"status": StatusChoice.ANNOTATION, "assignee": self.user.id}
        response = self._run_api_v1_jobs_id(self.job.id, None, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        response = self._run_api_v1_jobs_id(self.job.id + 10, None, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

class JobPartialUpdateAPITestCase(JobUpdateAPITestCase):
    def _run_api_v1_jobs_id(self, jid, user, data):
        if user:
            self.client.force_login(user, backend='django.contrib.auth.backends.ModelBackend')

        response = self.client.patch('/api/v1/jobs/{}'.format(jid), data=data, format='json')

        if user:
            self.client.logout()

        return response

    def test_api_v1_jobs_id_annotator_partial(self):
        data = {"status": StatusChoice.VALIDATION}
        response = self._run_api_v1_jobs_id(self.job.id, self.owner, data)
        self._check_request(response, data)

    def test_api_v1_jobs_id_admin_partial(self):
        data = {"assignee": self.user.id}
        response = self._run_api_v1_jobs_id(self.job.id, self.owner, data)
        self._check_request(response, data)
