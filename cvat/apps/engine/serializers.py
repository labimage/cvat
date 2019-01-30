# Copyright (C) 2019 Intel Corporation
#
# SPDX-License-Identifier: MIT

from rest_framework import serializers
from cvat.apps.engine.models import (Task, Job, Label, AttributeSpec,
    Segment)

from django.contrib.auth.models import User, Group

class AttributeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttributeSpec
        fields = ('id', 'text')

class LabelSerializer(serializers.ModelSerializer):
    attributes = AttributeSerializer(many=True, source='attributespec_set')
    class Meta:
        model = Label
        fields = ('id', 'name', 'attributes')

    def create(self, validated_data):
        attributes = validated_data.pop('attributes')
        label = Label.objects.create(**validated_data)
        for attr in attributes:
            AttributeSpec.objects.create(label=label, **attr)

        return label

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

class TaskSerializer(serializers.ModelSerializer):
    labels = LabelSerializer(many=True, source='label_set')
    segments = SegmentSerializer(many=True, source='segment_set', read_only=True)
    server_files = serializers.ListField(
        child=serializers.CharField(max_length=1024, trim_whitespace=True)
    )
    remote_files = serializers.ListField(
        child=serializers.CharField(max_length=1024)
    )


    class Meta:
        model = Task
        fields = ('url', 'id', 'name', 'size', 'mode', 'owner', 'assignee',
            'bug_tracker', 'created_date', 'updated_date', 'overlap',
            'segment_size', 'z_order', 'flipped', 'status', 'labels', 'segments',
            'server_files', 'client_files', 'remote_files')
        read_only_fields = ('size', 'mode', 'created_date', 'updated_date',
            'overlap', 'status', 'segment_size')
        write_only_fields = ('server_files', 'client_files', 'remote_files')

    def create(self, validated_data):
        labels = validated_data.pop('labels')
        task = Task.objects.create(**validated_data)
        for label in labels:
            Label.objects.create(task=task, **label)

        return task

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
