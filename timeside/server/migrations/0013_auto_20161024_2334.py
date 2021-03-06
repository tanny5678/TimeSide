# -*- coding: utf-8 -*-
# Generated by Django 1.9.10 on 2016-10-24 21:34
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('server', '0012_auto_20161004_1658'),
    ]

    operations = [
        migrations.AlterField(
            model_name='analysis',
            name='uuid',
            field=models.CharField(blank=True, editable=False, max_length=255, unique=True, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='analysistrack',
            name='uuid',
            field=models.CharField(blank=True, editable=False, max_length=255, unique=True, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='annotation',
            name='uuid',
            field=models.CharField(blank=True, editable=False, max_length=255, unique=True, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='annotationtrack',
            name='uuid',
            field=models.CharField(blank=True, editable=False, max_length=255, unique=True, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='experience',
            name='uuid',
            field=models.CharField(blank=True, editable=False, max_length=255, unique=True, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='item',
            name='uuid',
            field=models.CharField(blank=True, editable=False, max_length=255, unique=True, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='preset',
            name='uuid',
            field=models.CharField(blank=True, editable=False, max_length=255, unique=True, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='result',
            name='uuid',
            field=models.CharField(blank=True, editable=False, max_length=255, unique=True, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='selection',
            name='uuid',
            field=models.CharField(blank=True, editable=False, max_length=255, unique=True, verbose_name='uuid'),
        ),
        migrations.AlterField(
            model_name='task',
            name='uuid',
            field=models.CharField(blank=True, editable=False, max_length=255, unique=True, verbose_name='uuid'),
        ),
    ]
