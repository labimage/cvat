# Copyright (C) 2019 Intel Corporation
#
# SPDX-License-Identifier: MIT

from rest_framework import serializers
from cvat.apps.engine.models import (Task, Job, Label, AttributeSpec,
    Segment, ClientFile, ServerFile, RemoteFile, Plugin)

from django.contrib.auth.models import User, Group
import os
import shutil
import json

class AttributeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttributeSpec
        fields = ('id', 'text')

    def validate_text(self, value):
        attr = AttributeSpec.parse(value)
        if attr is None:
            message = "{} attribute value isn't correct".format(value)
            raise serializers.ValidationError(message)

        return value

class LabelSerializer(serializers.ModelSerializer):
    attributes = AttributeSerializer(many=True, source='attributespec_set',
        default=[])
    class Meta:
        model = Label
        fields = ('id', 'name', 'attributes')

class JobSerializer(serializers.ModelSerializer):
    task_id = serializers.ReadOnlyField(source="segment.task.id")
    start_frame = serializers.ReadOnlyField(source="segment.start_frame")
    stop_frame = serializers.ReadOnlyField(source="segment.stop_frame")

    class Meta:
        model = Job
        fields = ('url', 'id', 'assignee', 'status', 'start_frame',
            'stop_frame', 'max_shape_id', 'task_id')
        read_only_fields = ('max_shape_id',)

class SimpleJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = ('url', 'id', 'assignee', 'status', 'max_shape_id')
        read_only_fields = ('max_shape_id',)

class SegmentSerializer(serializers.ModelSerializer):
    jobs = SimpleJobSerializer(many=True, source='job_set')

    class Meta:
        model = Segment
        fields = ('start_frame', 'stop_frame', 'jobs')

class ClientFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientFile
        fields = ('file', )

    def to_internal_value(self, data):
        return {'file': data}

    def to_representation(self, instance):
        upload_dir = instance.task.get_upload_dirname()
        return instance.file.path[len(upload_dir) + 1:]

class ServerFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServerFile
        fields = ('file', )

class RemoteFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = RemoteFile
        fields = ('file', )

class RqStatusSerializer(serializers.Serializer):
    state = serializers.ChoiceField(choices=[
        "Queued", "Started", "Finished", "Failed"])
    message = serializers.CharField(allow_blank=True, default="")

class TaskDataSerializer(serializers.ModelSerializer):
    client_files = ClientFileSerializer(many=True, source='clientfile_set',
        default=[])
    server_files = ServerFileSerializer(many=True, source='serverfile_set',
        default=[])
    remote_files = RemoteFileSerializer(many=True, source='remotefile_set',
        default=[])

    class Meta:
        model = Task
        fields = ('client_files', 'server_files', 'remote_files')

    def update(self, instance, validated_data):
        client_files = validated_data.pop('clientfile_set')
        server_files = validated_data.pop('serverfile_set')
        remote_files = validated_data.pop('remotefile_set')

        for file in client_files:
            client_file = ClientFile(task=instance, **file)
            client_file.save()

        for file in server_files:
            server_file = ServerFile(task=instance, **file)
            server_file.save()

        for file in remote_files:
            remote_file = RemoteFile(task=instance, **file)
            remote_file.save()

        return instance


class TaskSerializer(serializers.ModelSerializer):
    labels = LabelSerializer(many=True, source='label_set', partial=True)
    segments = SegmentSerializer(many=True, source='segment_set', read_only=True)
    image_quality = serializers.IntegerField(min_value=0, max_value=100,
        default=50)

    class Meta:
        model = Task
        fields = ('url', 'id', 'name', 'size', 'mode', 'owner', 'assignee',
            'bug_tracker', 'created_date', 'updated_date', 'overlap',
            'segment_size', 'z_order', 'flipped', 'status', 'labels', 'segments',
            'image_quality')
        read_only_fields = ('size', 'mode', 'created_date', 'updated_date',
            'overlap', 'status', 'segment_size')
        ordering = ['-id']

    def create(self, validated_data):
        labels = validated_data.pop('label_set')
        if not validated_data.get('segment_size'):
            validated_data['segment_size'] = 0
        db_task = Task.objects.create(size=0, **validated_data)
        for label in labels:
            attributes = label.pop('attributespec_set')
            db_label = Label.objects.create(task=db_task, **label)
            for attr in attributes:
                AttributeSpec.objects.create(label=db_label, **attr)

        task_path = db_task.get_task_dirname()
        if os.path.isdir(task_path):
            shutil.rmtree(task_path)

        upload_dir = db_task.get_upload_dirname()
        os.makedirs(upload_dir)
        output_dir = db_task.get_data_dirname()
        os.makedirs(output_dir)

        return db_task

class UserSerializer(serializers.ModelSerializer):
    groups = serializers.SlugRelatedField(many=True,
        slug_field='name', queryset=Group.objects.all())

    class Meta:
        model = User
        fields = ('url', 'id', 'username', 'first_name', 'last_name', 'email',
            'groups', 'is_staff', 'is_superuser', 'is_active', 'last_login',
            'date_joined', 'groups')
        read_only_fields = ('last_login', 'date_joined')
        write_only_fields = ('password', )

class ExceptionSerializer(serializers.Serializer):
    task = serializers.IntegerField()
    job = serializers.IntegerField()
    message = serializers.CharField(max_length=1000)
    filename = serializers.URLField()
    line = serializers.IntegerField()
    column = serializers.IntegerField()
    stack = serializers.CharField(max_length=10000,
        style={'base_template': 'textarea.html'})
    browser = serializers.CharField(max_length=255)
    os = serializers.CharField(max_length=255)

class AboutSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=128)
    description = serializers.CharField(max_length=2048)
    version = serializers.CharField(max_length=64)

class ImageMetaSerializer(serializers.Serializer):
    width = serializers.IntegerField()
    height = serializers.IntegerField()

class PluginSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plugin
        fields = ('name', 'description', 'maintainer', 'created_at',
            'updated_at')
