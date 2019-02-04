# Copyright (C) 2018 Intel Corporation
#
# SPDX-License-Identifier: MIT

from rest_framework import versioning

class URLPathVersioning(versioning.URLPathVersioning):
    def determine_version(self, request, *args, **kwargs):
        # When you try to specify a version (e.g /api/v1/docs) it will generate
        # an error inside a template of Rest Framework (reverse of an URL
        # without argument). Also when you try don't use version at all it will
        # give you an error 'invalid version'. To avoid these problems just
        # redefine determine_version for /api/docs/*.
        if request.path.startswith('/api/docs/'):
            return None

        return super().determine_version(request, *args, **kwargs)