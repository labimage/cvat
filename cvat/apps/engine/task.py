
# Copyright (C) 2018 Intel Corporation
#
# SPDX-License-Identifier: MIT

import os
import sys
import rq
import shlex
import shutil
import tempfile
from PIL import Image
from traceback import print_exception
from ast import literal_eval

import mimetypes
_SCRIPT_DIR = os.path.realpath(os.path.dirname(__file__))
_MEDIA_MIMETYPES_FILE = os.path.join(_SCRIPT_DIR, "media.mimetypes")
mimetypes.init(files=[_MEDIA_MIMETYPES_FILE])

from cvat.apps.engine.models import StatusChoice
from cvat.apps.engine.plugins import plugin_decorator

import django_rq
from django.conf import settings
from django.db import transaction
from ffmpy import FFmpeg
from pyunpack import Archive
from distutils.dir_util import copy_tree
from collections import OrderedDict

from . import models
from .log import slogger

############################# Low Level server API

def create(tid, data):
    """Schedule the task"""
    q = django_rq.get_queue('default')
    q.enqueue_call(func=_create_thread, args=(tid, data),
        job_id="/api/v1/tasks/{}".format(tid))

def get_frame_path(tid, frame):
    """Read corresponding frame for the task"""
    db_task = models.Task.objects.get(pk=tid)
    path = _get_frame_path(frame, db_task.get_data_dirname())

    return path


@transaction.atomic
def rq_handler(job, exc_type, exc_value, traceback):
    tid = job.id.split('/')[1]
    db_task = models.Task.objects.select_for_update().get(pk=tid)
    with open(db_task.get_log_path(), "wt") as log_file:
        print_exception(exc_type, exc_value, traceback, file=log_file)
    db_task.delete()

    return False

############################# Internal implementation for server API

class _FrameExtractor:
    def __init__(self, source_path, compress_quality, flip_flag=False):
        # translate inversed range 1:95 to 2:32
        translated_quality = 96 - compress_quality
        translated_quality = round((((translated_quality - 1) * (31 - 2)) / (95 - 1)) + 2)
        self.output = tempfile.mkdtemp(prefix='cvat-', suffix='.data')
        target_path = os.path.join(self.output, '%d.jpg')
        output_opts = '-start_number 0 -b:v 10000k -vsync 0 -an -y -q:v ' + str(translated_quality)
        if flip_flag:
            output_opts += ' -vf "transpose=2,transpose=2"'
        ff = FFmpeg(
            inputs  = {source_path: None},
            outputs = {target_path: output_opts})
        ff.run()

    def getframepath(self, k):
        return "{0}/{1}.jpg".format(self.output, k)

    def __del__(self):
        if self.output:
            shutil.rmtree(self.output)

    def __getitem__(self, k):
        return self.getframepath(k)

    def __iter__(self):
        i = 0
        while os.path.exists(self.getframepath(i)):
            yield self[i]
            i += 1

def make_image_meta_cache(db_task):
    with open(db_task.get_image_meta_cache_path(), 'w') as meta_file:
        cache = {
            'original_size': []
        }

        if db_task.mode == 'interpolation':
            image = Image.open(get_frame_path(db_task.id, 0))
            cache['original_size'].append({
                'width': image.size[0],
                'height': image.size[1]
            })
            image.close()
        else:
            filenames = []
            for root, _, files in os.walk(db_task.get_upload_dirname()):
                fullnames = map(lambda f: os.path.join(root, f), files)
                images = filter(lambda x: _get_mime(x) == 'image', fullnames)
                filenames.extend(images)
            filenames.sort()

            for image_path in filenames:
                image = Image.open(image_path)
                cache['original_size'].append({
                    'width': image.size[0],
                    'height': image.size[1]
                })
                image.close()

        meta_file.write(str(cache))


def get_image_meta_cache(db_task):
    try:
        with open(db_task.get_image_meta_cache_path()) as meta_cache_file:
            return literal_eval(meta_cache_file.read())
    except Exception:
        make_image_meta_cache(db_task)
        with open(db_task.get_image_meta_cache_path()) as meta_cache_file:
            return literal_eval(meta_cache_file.read())


def _get_mime(name):
    mime = mimetypes.guess_type(name)
    mime_type = mime[0]
    encoding = mime[1]
    # zip, rar, tar, tar.gz, tar.bz2, 7z, cpio
    supportedArchives = ['application/zip', 'application/x-rar-compressed',
        'application/x-tar', 'application/x-7z-compressed', 'application/x-cpio',
        'gzip', 'bzip2']
    if mime_type is not None:
        if mime_type.startswith('video'):
            return 'video'
        elif mime_type in supportedArchives or encoding in supportedArchives:
            return 'archive'
        elif mime_type.startswith('image'):
            return 'image'
        else:
            return 'empty'
    else:
        if os.path.isdir(name):
            return 'directory'
        else:
            return 'empty'


def _get_frame_path(frame, base_dir):
    d1 = str(int(frame) // 10000)
    d2 = str(int(frame) // 100)
    path = os.path.join(d1, d2, str(frame) + '.jpg')
    if base_dir:
        path = os.path.join(base_dir, path)

    return path



'''
    Count all files, remove garbage (unknown mime types or extra dirs)
'''
def _prepare_paths(source_paths, target_paths, storage):
    counters = {
        "image": 0,
        "directory": 0,
        "video": 0,
        "archive": 0
    }

    share_dirs_mapping = {}
    share_files_mapping = {}

    if storage == 'local':
        # Files were uploaded early. Remove trash if it exists. Count them.
        for path in target_paths:
            mime = _get_mime(path)
            if mime in ['video', 'archive', 'image']:
                counters[mime] += 1
            else:
                try:
                    os.remove(path)
                except:
                    os.rmdir(path)
    else:
        # Files are available via mount share. Count them and separate dirs.
        for source_path, target_path in zip(source_paths, target_paths):
            mime = _get_mime(source_path)
            if mime in ['directory', 'image', 'video', 'archive']:
                counters[mime] += 1
                if mime == 'directory':
                    share_dirs_mapping[source_path] = target_path
                else:
                    share_files_mapping[source_path] = target_path

        # Remove directories if other files from them exists in input paths
        exclude = []
        for dir_name in share_dirs_mapping.keys():
            for patch in share_files_mapping.keys():
                if dir_name in patch:
                    exclude.append(dir_name)
                    break

        for excluded_dir in exclude:
            del share_dirs_mapping[excluded_dir]

        counters['directory'] = len(share_dirs_mapping.keys())

    return (counters, share_dirs_mapping, share_files_mapping)


'''
    Check file set on valid
    Valid if:
        1 video, 0 images and 0 dirs (interpolation mode)
        1 archive, 0 images and 0 dirs (annotation mode)
        Many images or many dirs with images (annotation mode), 0 archives and 0 videos
'''
def _valid_file_set(counters):
    if (counters['image'] or counters['directory']) and (counters['video'] or counters['archive']):
        return False
    elif counters['video'] > 1 or (counters['video'] and (counters['archive'] or counters['image'] or counters['directory'])):
        return False
    elif counters['archive'] > 1 or (counters['archive'] and (counters['video'] or counters['image'] or counters['directory'])):
        return False

    return True


'''
    Copy data from share to local
'''
def _copy_data_from_share(share_data):
    for source_path in share_dirs_mapping:
        copy_tree(source_path, share_dirs_mapping[source_path])
    for source_path in share_files_mapping:
        target_path = share_files_mapping[source_path]
        target_dir = os.path.dirname(target_path)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)
        shutil.copyfile(source_path, target_path)


'''
    Find and unpack archive in upload dir
'''
def _find_and_unpack_archive(upload_dir):
    archive = None
    for root, _, files in os.walk(upload_dir):
        fullnames = map(lambda f: os.path.join(root, f), files)
        archives = list(filter(lambda x: _get_mime(x) == 'archive', fullnames))
        if len(archives):
            archive = archives[0]
            break
    if archive:
        Archive(archive).extractall(upload_dir)
        os.remove(archive)
    else:
        raise Exception('Type defined as archive, but archives were not found.')

    return archive


'''
    Search a video in upload dir and split it by frames. Copy frames to target dirs
'''
def _find_and_extract_video(upload_dir, output_dir, db_task, compress_quality, flip_flag, job):
    video = None
    for root, _, files in os.walk(upload_dir):
        fullnames = map(lambda f: os.path.join(root, f), files)
        videos = list(filter(lambda x: _get_mime(x) == 'video', fullnames))
        if len(videos):
            video = videos[0]
            break

    if video:
        job.meta['status'] = 'Video is being extracted..'
        job.save_meta()
        extractor = _FrameExtractor(video, compress_quality, flip_flag)
        for frame, image_orig_path in enumerate(extractor):
            image_dest_path = _get_frame_path(frame, output_dir)
            db_task.size += 1
            dirname = os.path.dirname(image_dest_path)
            if not os.path.exists(dirname):
                os.makedirs(dirname)
            shutil.copyfile(image_orig_path, image_dest_path)
    else:
        raise Exception("Video files were not found")

    return video


'''
    Recursive search for all images in upload dir and compress it to RGB jpg with specified quality. Create symlinks for them.
'''
def _find_and_compress_images(upload_dir, output_dir, db_task, compress_quality, flip_flag, job):
    filenames = []
    for root, _, files in os.walk(upload_dir):
        fullnames = map(lambda f: os.path.join(root, f), files)
        images = filter(lambda x: _get_mime(x) == 'image', fullnames)
        filenames.extend(images)
    filenames.sort()

    if len(filenames):
        for idx, name in enumerate(filenames):
            job.meta['status'] = 'Images are being compressed.. {}%'.format(idx * 100 // len(filenames))
            job.save_meta()
            compressed_name = os.path.splitext(name)[0] + '.jpg'
            image = Image.open(name).convert('RGB')
            if flip_flag:
                image = image.transpose(Image.ROTATE_180)
            image.save(compressed_name, quality=compress_quality, optimize=True)
            image.close()
            if compressed_name != name:
                os.remove(name)
                # PIL::save uses filename in order to define image extension.
                # We need save it as jpeg for compression and after rename the file
                # Else annotation file will contain invalid file names (with other extensions)
                os.rename(compressed_name, name)

        for frame, image_orig_path in enumerate(filenames):
            image_dest_path = _get_frame_path(frame, output_dir)
            image_orig_path = os.path.abspath(image_orig_path)
            db_task.size += 1
            dirname = os.path.dirname(image_dest_path)
            if not os.path.exists(dirname):
                os.makedirs(dirname)
            os.symlink(image_orig_path, image_dest_path)
    else:
        raise Exception("Image files were not found")

    return filenames

def _save_task_to_db(db_task, task_params):
    segment_step = task_params['segment'] - db_task.overlap
    for x in range(0, db_task.size, segment_step):
        start_frame = x
        stop_frame = min(x + task_params['segment'] - 1, db_task.size - 1)
        slogger.glob.info("New segment for task #{}: start_frame = {}, \
            stop_frame = {}".format(db_task.id, start_frame, stop_frame))

        db_segment = models.Segment()
        db_segment.task = db_task
        db_segment.start_frame = start_frame
        db_segment.stop_frame = stop_frame
        db_segment.save()

        db_job = models.Job()
        db_job.segment = db_segment
        db_job.save()

    db_task.save()


@transaction.atomic
def _create_thread(tid, data):
    slogger.glob.info("create task #{}".format(tid))
    job = rq.get_current_job()

    db_task = models.Task.objects.select_for_update().get(pk=tid)
    upload_dir = db_task.get_upload_dirname()
    output_dir = db_task.get_data_dirname()

    # Validate that uploaded files are OK (number of images, videos, archives)


    # counters, share_dirs_mapping, share_files_mapping = _prepare_paths(
    #     params['SOURCE_PATHS'],
    #     params['TARGET_PATHS'],
    #     params['storage']
    # )

    if (not _valid_file_set(counters)):
        raise ValueError('Only one archive, one video or many images can be \
            dowloaded simultaneously. {} image(s), {} dir(s), {} video(s), {} \
            archive(s) found'.format(
                counters['image'],
                counters['directory'],
                counters['video'],
                counters['archive']
            )
        )

    if data['server_files']:
        job.meta['status'] = 'Data are being copied from share..'
        job.save_meta()
        #_copy_data_from_share(data['server_files'])

    archive = None
    if counters['archive']:
        job.meta['status'] = 'Archive is being unpacked..'
        job.save_meta()
        archive = _find_and_unpack_archive(upload_dir)

    # Define task mode and other parameters
    task_params = {
        'mode': 'annotation' if counters['image'] or counters['directory'] or counters['archive'] else 'interpolation',
    }

    if task_params['mode'] == 'interpolation':
        video = _find_and_extract_video(upload_dir, output_dir, db_task,
            task_params['compress'], task_params['flip'], job)
        task_params['data'] = os.path.relpath(video, upload_dir)
    else:
        files =_find_and_compress_images(upload_dir, output_dir, db_task,
            task_params['compress'], task_params['flip'], job)
        if archive:
            task_params['data'] = os.path.relpath(archive, upload_dir)
        else:
            task_params['data'] = '{} images: {}, ...'.format(len(files),
                ", ".join([os.path.relpath(x, upload_dir) for x in files[0:2]]))

    slogger.glob.info("Founded frames {} for task #{}".format(db_task.size, tid))

    job.meta['status'] = 'Task is being saved in database'
    job.save_meta()
    _save_task_to_db(db_task, task_params)
