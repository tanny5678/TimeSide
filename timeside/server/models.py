# -*- coding: utf-8 -*-
#
# Copyright (c) 2014-2016 Parisson SARL
# Copyright (c) 2014-2016 Guillaume Pellerin <yomguy@parisson.com>
# Copyright (c) 2014-2016 Thomas Fillon <thomas@parisson.com>

# This file is part of TimeSide.

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Authors:
# Guillaume Pellerin <yomguy@parisson.com>
# Thomas Fillon <thomas@parisson.com>


import os
import uuid
import mimetypes
import ast
import time

import timeside.core
from timeside.plugins.decoder.utils import sha1sum_file, sha1sum_url
from timeside.core.tools.parameters import DEFAULT_SCHEMA

from django.db import models
from django.utils.functional import lazy
from django.utils.translation import ugettext_lazy as _
from django.contrib.auth.models import User
from django.db.models.signals import post_save, pre_save
from django.conf import settings
import jsonfield
import json

app = 'timeside'

processors = timeside.core.processor.processors(timeside.core.api.IProcessor)

_processor_types = {'Analyzers': timeside.core.api.IAnalyzer,
                    'Encoders': timeside.core.api.IEncoder,
                    'Graphers': timeside.core.api.IGrapher}


def get_processor_pids():
    return [(name, [(processor.id(), processor.id())
                    for processor
                    in timeside.core.processor.processors(proc_type)])
            for name, proc_type in _processor_types.items()]

public_extra_types = {
    '.webm': 'video/webm',
}

encoders = timeside.core.processor.processors(timeside.core.api.IEncoder)
for encoder in encoders:
    public_extra_types['.' + encoder.file_extension()] = encoder.mime_type()

private_extra_types = {
    '.eaf': 'text/xml',  # ELAN Annotation Format
    '.trs': 'text/xml',  # Trancriber Annotation Format
    '.svl': 'text/xml',  # Sonic Visualiser layer file
    '.TextGrid': 'text/praat-textgrid',  # Praat TextGrid annotation file
}

for ext, mime_type in public_extra_types.items():
    mimetypes.add_type(mime_type, ext)

for ext, mime_type in private_extra_types.items():
    mimetypes.add_type(mime_type, ext)


# Status
_FAILED, _DRAFT, _PENDING, _RUNNING, _DONE = 0, 1, 2, 3, 4
STATUS = ((_FAILED, _('failed')), (_DRAFT, _('draft')),
          (_PENDING, _('pending')), (_RUNNING, _('running')),
          (_DONE, _('done')))


RESULTS_ROOT = os.path.join(settings.MEDIA_ROOT, 'results')
if not os.path.exists(RESULTS_ROOT):
    os.makedirs(RESULTS_ROOT)


def get_mime_type(path):
    return mimetypes.guess_type(path)[0]


# --- Abstract classes -----
class Dated(models.Model):

    date_added = models.DateTimeField(_('date added'), auto_now_add=True, null=True)
    date_modified = models.DateTimeField(_('date modified'), auto_now=True, null=True)

    class Meta:
        abstract = True


class UUID(models.Model):

    uuid = models.CharField(_('uuid'), unique=True, blank=True, max_length=255, editable=False)

    class Meta:
        abstract = True

    def save(self, **kwargs):
        if not self.uuid:
            self.uuid = uuid.uuid4()
        super(UUID, self).save(**kwargs)


class Titled(models.Model):

    title = models.CharField(_('title'), blank=True, max_length=512)
    description = models.TextField(_('description'), blank=True)

    def __unicode__(self):
        return self.title

    class Meta:
        abstract = True


class Shareable(models.Model):

    author = models.ForeignKey(User, related_name="%(class)s", verbose_name=_('author'), blank=True, null=True, on_delete=models.SET_NULL)
    is_public = models.BooleanField(default=True)

    class Meta:
        abstract = True


# ----- Timeside server models ------

class Selection(Titled, UUID, Dated, Shareable):

    items = models.ManyToManyField('Item', related_name="selections", verbose_name=_('items'), blank=True)
    selections = models.ManyToManyField('Selection', related_name="other_selections", verbose_name=_('other selections'), blank=True)

    class Meta:
        db_table = app + '_selections'
        verbose_name = _('selection')

    def get_all_items(self):
        qs_items = self.items.all()
        for selection in self.selections.all():
            qs_items |= selection.get_all_items()
        return qs_items


class Item(Titled, UUID, Dated, Shareable):

    element_type = 'timeside_item'

    source_file = models.FileField(_('file'), upload_to='items/%Y/%m/%d', blank=True, max_length=1024)
    source_url = models.URLField(_('URL'), blank=True, max_length=1024)
    sha1 = models.CharField(_('sha1'), blank=True, max_length=512)
    mime_type = models.CharField(_('mime type'), blank=True, max_length=256)
    hdf5 = models.FileField(_('HDF5 result file'), upload_to='results/%Y/%m/%d', blank=True, max_length=1024)
    lock = models.BooleanField(default=False)

    class Meta:
        db_table = app + '_items'
        ordering = ['title']
        verbose_name = _('item')

    def results(self):
        return [result for result in self.results.all()]

    def lock_setter(self, lock):
        self.lock = lock
        self.save()

    def get_uri(self):
        """Return the Item source"""
        if self.source_file and os.path.exists(self.source_file.path):
            return self.source_file.path
        elif self.source_url:
            return self.source_url
        return None

    def get_audio_duration(self):
        """
        Return item audio duration
        """
        decoder = timeside.core.get_processor('file_decoder')(
            uri=self.get_uri())
        return decoder.uri_total_duration

    def get_results_path(self):
        """
        Return Item result path
        """
        result_path = os.path.join(RESULTS_ROOT, self.uuid)
        if not os.path.exists(result_path):
            os.makedirs(result_path)
        return result_path

    def get_single_selection(self):
        # TODO : have singleton selection has a foreign key of Item ???
        sel_title = "Singleton selection for item %d" % self.id
        sel_description = ("Singleton selection for item %d\n"
                           "Automatically generated by the TimeSide "
                           "application.") % self.id
        selection, created = Selection.objects.get_or_create(
            title=sel_title,
            description=sel_description)
        if created:
            selection.save()
            selection.items.add(self)
        return selection

    def run(self, experience):
        result_path = self.get_results_path()
        uri = self.get_uri()

        decoder = timeside.plugins.decoder.file.FileDecoder(uri=uri,
                                                            sha1=self.sha1)
        presets = {}
        pipe = decoder
        for preset in experience.presets.all():
            proc = preset.processor.get_processor()
            if proc.type == 'encoder':
                result, c = Result.objects.get_or_create(preset=preset,
                                                         item=self)
                media_file = '.'.join([str(result.uuid),
                                       proc.file_extension()])
                result.file = os.path.join(result_path, media_file)
                result.save()
                proc = proc(result.file.path, overwrite=True,
                            streaming=False)
            elif proc.type in ['analyzer', 'grapher']:
                print json.loads(preset.parameters)
                proc = proc(**json.loads(preset.parameters))

            presets[preset] = proc
            pipe |= proc

        # item.lock_setter(True)

        if not self.hdf5:
            hdf5_file = str(experience.uuid) + '.hdf5'
            self.hdf5 = os.path.join(result_path, hdf5_file)
            self.save()

        pipe.run()

        def set_results_from_processor(proc, preset=None):
            for result_id in proc.results.keys():
                parameters = proc.results[result_id].parameters
            if preset is None:
                processor, c = Processor.objects.get_or_create(pid=proc.id())
                presets = Preset.objects.filter(processor=processor,
                                                parameters=json.dumps(parameters))
                if presets:
                    preset = presets[0]
                else:
                    preset = Preset(processor=processor,
                                    parameters=json.dumps(parameters))
                    preset.save()
            else:
                processor = preset.processor

            result, c = Result.objects.get_or_create(preset=preset,
                                                     item=self)
            hdf5_file = str(result.uuid) + '.hdf5'
            result.hdf5 = os.path.join(result_path, hdf5_file)
            # while result.lock:
            #     time.sleep(3)
            # result.lock_setter(True)
            proc.results.to_hdf5(result.hdf5.path)
            # result.lock_setter(False)
            result.status_setter(_DONE)

        for preset, proc in presets.iteritems():
            if proc.type == 'analyzer':
                # TODO : set_proc_results
                set_results_from_processor(proc, preset)

            elif proc.type == 'grapher':
                result, c = Result.objects.get_or_create(preset=preset,
                                                         item=self)
                image_file = str(result.uuid) + '.png'
                result.file = os.path.join(result_path, image_file)
                # TODO : set as an option
                proc.watermark('timeside', opacity=.6, margin=(5, 5))
                proc.render(output=result.file.path)
                result.mime_type_setter(get_mime_type(result.file.path))
                result.status_setter(_DONE)

                if 'analyzer' in proc.parents:
                    analyzer = proc.parents['analyzer']
                    set_results_from_processor(analyzer)

            elif proc.type == 'encoder':
                result = Result.objects.get(preset=preset, item=self)
                result.mime_type_setter(get_mime_type(result.file.path))
                result.status_setter(_DONE)

            del proc

        del pipe
        # item.lock_setter(False)


class Experience(Titled, UUID, Dated, Shareable):

    presets = models.ManyToManyField('Preset', related_name="experiences", verbose_name=_('presets'), blank=True)
    experiences = models.ManyToManyField('Experience', related_name="other_experiences", verbose_name=_('other experiences'), blank=True)

    class Meta:
        db_table = app + '_experiences'
        verbose_name = _('Experience')


class Processor(models.Model):

    pid = models.CharField(_('pid'), unique=True, max_length=128)
    version = models.CharField(_('version'), max_length=64, blank=True)
    name = models.CharField(_('name'), max_length=256, blank=True)

    def __init__(self, *args, **kwargs):
        super(Processor, self).__init__(*args, **kwargs)
        self._meta.get_field('pid')._choices = lazy(get_processor_pids, list)()

    class Meta:
        db_table = app + '_processors'
        verbose_name = _('processor')

    def __unicode__(self):
        return '_'.join([self.pid, str(self.id)])

    def save(self, **kwargs):
        if not self.version:
            self.version = timeside.core.__version__
        if not self.name:
            try:
                self.name = self.get_processor().name()
            except AttributeError:
                pass
        super(Processor, self).save(**kwargs)

    def get_processor(self):
        return timeside.core.get_processor(self.pid)

    def get_parameters_schema(self):
        return self.get_processor().get_parameters_schema()

    def get_parameters_default(self):
        return self.get_processor().get_parameters_default()


class SubProcessor(models.Model):
    """SubProcessor object are intended to store the different results id associated with a given Processor
    """
    sub_processor_id = models.CharField(_('sub_processor_id'), unique=True, max_length=128)
    name = models.CharField(_('name'), max_length=256, blank=True)

    processor = models.ForeignKey('Processor', related_name="sub_results", verbose_name=_('processor'), blank=True, null=True)

    class Meta:
        db_table = app + '_subprocessors'
        verbose_name = _('Subprocessor')

    def __unicode__(self):
        return self.sub_processor_id


class Preset(UUID, Dated, Shareable):

    processor = models.ForeignKey('Processor', related_name="presets", verbose_name=_('processor'), blank=True, null=True)
    parameters = models.TextField(_('Parameters'), blank=True, default='{}')
    # TODO : turn this filed into a JSON Field
    # see : http://stackoverflow.com/questions/22600056/django-south-changing-field-type-in-data-migration

    class Meta:
        db_table = app + '_presets'
        verbose_name = _('Preset')
        verbose_name_plural = _('Presets')

    def __unicode__(self):
        return '_'.join([unicode(self.processor), str(self.id)])

    def get_single_experience(self):
        exp_title = "Simple experience for preset %d" % self.id
        exp_description = "\n".join([exp_title,
                                     "Automatically generated by the TimeSide application."])
        experience, created = Experience.objects.get_or_create(title=exp_title,
                                                               description=exp_description)
        if created:
            experience.save()
            experience.presets.add(self)
        elif (experience.presets.count() > 1) or (self not in experience.presets.all()):
            experience.presets.clear()
            experience.presets.add(self)

        return experience


class Result(UUID, Dated, Shareable):

    item = models.ForeignKey('Item', related_name="results", verbose_name=_('item'), blank=True, null=True, on_delete=models.SET_NULL)
    preset = models.ForeignKey('Preset', related_name="results", verbose_name=_('preset'), blank=True, null=True, on_delete=models.SET_NULL)
    hdf5 = models.FileField(_('HDF5 result file'), upload_to='results/%Y/%m/%d', blank=True, max_length=1024)
    file = models.FileField(_('Output file'), upload_to='results/%Y/%m/%d', blank=True, max_length=1024)
    mime_type = models.CharField(_('Output file MIME type'), blank=True, max_length=256)
    status = models.IntegerField(_('status'), choices=STATUS, default=_DRAFT)

    # lock = models.BooleanField(default=False)

    class Meta:
        db_table = app + '_results'
        verbose_name = _('Result')
        verbose_name_plural = _('Results')

    def status_setter(self, status):
        self.status = status
        self.save()

    def mime_type_setter(self, mime_type):
        self.mime_type = mime_type
        self.save()

    def lock_setter(self, lock):
        self.lock = lock
        self.save()

    def __unicode__(self):
        return '_'.join([self.item.title, unicode(self.preset.processor)])


class Task(UUID, Dated, Shareable):

    experience = models.ForeignKey('Experience', related_name="task", verbose_name=_('experience'), blank=True, null=True)
    selection = models.ForeignKey('Selection', related_name="task", verbose_name=_('selection'), blank=True, null=True)
    status = models.IntegerField(_('status'), choices=STATUS, default=_DRAFT)

    class Meta:
        db_table = app + '_tasks'
        verbose_name = _('Task')
        verbose_name_plural = _('Tasks')

    def __unicode__(self):
        return '_'.join([unicode(self.selection), unicode(self.experience), unicode(self.id)])

    def status_setter(self, status):
        self.status = status
        self.save()

    def is_done(self):
        return (self.status == _DONE)

    def run(self, wait=False, streaming=False):
        self.status_setter(_RUNNING)

        from timeside.server.tasks import task_run
        task_run.delay(task_id=self.id)

        if wait:
            status = Task.objects.get(id=self.id).status
            while (status != _DONE):
                time.sleep(0.5)
                status = Task.objects.get(id=self.id).status


def set_mimetype(sender, **kwargs):
    instance = kwargs['instance']
    if (sender == Result) and instance.file:
        path = instance.file.path
    elif (sender == Item):
        if instance.source_url:
            path = instance.source_url
        elif instance.source_file:
            path = instance.source_file.path
    else:
        return
    mime_type = get_mime_type(path)
    if instance.mime_type == mime_type:
        return
    else:
        instance.mime_type = get_mime_type(path)
        super(sender, instance).save()


def set_hash(sender, **kwargs):
    instance = kwargs['instance']
    if instance.source_file:
        sha1 = sha1sum_file(instance.source_file.path)
    elif instance.source_url:
        sha1 = sha1sum_url(instance.source_url)
    else:
        return
    if instance.sha1 == sha1:
        return
    else:
        instance.sha1 = sha1
        super(sender, instance).save()


def run(sender, **kwargs):
    task = kwargs['instance']
    if task.status == _PENDING:
        task.run()


post_save.connect(set_mimetype, sender=Item)
post_save.connect(set_hash, sender=Item)
post_save.connect(set_mimetype, sender=Result)
post_save.connect(run, sender=Task)


# Session and Tracks related objects

class Analysis(Titled, UUID, Dated, Shareable):
    sub_processor = models.ForeignKey(SubProcessor, related_name="analysis", verbose_name=_('sub_processor'), blank=False)
    preset = models.ForeignKey(Preset, related_name="analysis", verbose_name=_('preset'), blank=False)
    parameters_schema = jsonfield.JSONField(default=DEFAULT_SCHEMA())

    class Meta:
        db_table = app + '_analysis'
        verbose_name = _('Analysis')
        verbose_name_plural = _('Analyses')


class AnalysisTrack(Titled, UUID, Dated, Shareable):

    analysis = models.ForeignKey(Analysis, related_name='tracks', verbose_name=_('analysis'), blank=False)
    item = models.ForeignKey(Item, related_name='analysis_tracks', verbose_name=_('item'), blank=False)

    class Meta:
        db_table = app + '_analysis_tracks'
        verbose_name = _('Analysis Track')


class AnnotationTrack(Titled, UUID, Dated, Shareable):

    item = models.ForeignKey(Item, related_name='annotation_tracks', verbose_name=_('item'), blank=False)  # noqa
    overlapping = models.BooleanField(default=False)

    class Meta:
        db_table = app + '_annotation_tracks'
        verbose_name = _('Annotation Track')


class Annotation(Titled, UUID, Dated, Shareable):

    track = models.ForeignKey(AnnotationTrack, related_name='annotations', verbose_name=_('annotation'), blank=False)
    start_time = models.FloatField(_('start time (s)'), default=0)
    stop_time = models.FloatField(_('stop time (s)'))
