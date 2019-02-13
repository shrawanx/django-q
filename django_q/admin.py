"""Admin module for Django."""
from django.contrib import admin
from django.contrib.admin.utils import unquote
from django.core.exceptions import PermissionDenied
from django.template.response import TemplateResponse
from django.utils.translation import ugettext_lazy as _
from django.urls import path

from django_q.conf import Conf
from django_q.models import Success, Failure, Schedule, OrmQ, Task
from django_q.tasks import async_task


class TaskAdmin(admin.ModelAdmin):
    """model admin for success tasks."""

    list_display = (
        u'name',
        'func',
        'started',
        'stopped',
        'time_taken',
        'group'
    )

    def has_add_permission(self, request):
        """Don't allow adds."""
        return False

    def get_queryset(self, request):
        """Only show successes."""
        qs = super(TaskAdmin, self).get_queryset(request)
        return qs.filter(success=True)

    search_fields = ('name', 'func', 'group')
    readonly_fields = []
    list_filter = ('group',)

    def get_readonly_fields(self, request, obj=None):
        """Set all fields readonly."""
        return list(self.readonly_fields) + [field.name for field in obj._meta.fields]


def retry_failed(FailAdmin, request, queryset):
    """Submit selected tasks back to the queue."""
    for task in queryset:
        async_task(task.func, *task.args or (), hook=task.hook, **task.kwargs or {})
        task.delete()


retry_failed.short_description = _("Resubmit selected tasks to queue")


class FailAdmin(admin.ModelAdmin):
    """model admin for failed tasks."""

    list_display = (
        'name',
        'func',
        'started',
        'stopped',
        'short_result'
    )

    def has_add_permission(self, request):
        """Don't allow adds."""
        return False

    actions = [retry_failed]
    search_fields = ('name', 'func')
    list_filter = ('group',)
    readonly_fields = []

    def get_readonly_fields(self, request, obj=None):
        """Set all fields readonly."""
        return list(self.readonly_fields) + [field.name for field in obj._meta.fields]


class ScheduleAdmin(admin.ModelAdmin):
    """ model admin for schedules """

    list_display = (
        'id',
        'name',
        'func',
        'schedule_type',
        'task_type',
        'repeats',
        'next_run',
        'last_run',
        'success'
    )

    list_filter = ('next_run', 'schedule_type')
    search_fields = ('func',)
    list_display_links = ('id', 'name')

    def get_urls(self):
        _urls = super().get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name

        return [
            path('<path:object_id>/run-history/', self.task_run_view, name='%s_%s_run_history' % info),
        ] + _urls

    def task_run_view(self, request, object_id, extra_context=None):
        model = self.model
        obj = self.get_object(request, unquote(object_id))
        if obj is None:
            return self._get_obj_does_not_exist_redirect(request, model._meta, object_id)

        if not self.has_view_or_change_permission(request, obj):
            raise PermissionDenied

        opts = model._meta
        run_histories = Task.objects.filter(
            func=obj.func,
        ).order_by('-id')
        context = {
            **self.admin_site.each_context(request),
            'title': _('Schedule Task Run Histories: %s') % obj,
            'object': obj,
            'run_histories': run_histories,
            'opts': opts,
            'preserved_filters': self.get_preserved_filters(request),
            **(extra_context or {}),
        }

        request.current_app = self.admin_site.name

        return TemplateResponse(request, 'admin/django_q/schedule/run_histories.html', context)


class QueueAdmin(admin.ModelAdmin):
    """  queue admin for ORM broker """
    list_display = (
        'id',
        'key',
        'task_id',
        'name',
        'func',
        'lock'
    )

    def save_model(self, request, obj, form, change):
        obj.save(using=Conf.ORM)

    def delete_model(self, request, obj):
        obj.delete(using=Conf.ORM)

    def get_queryset(self, request):
        return super(QueueAdmin, self).get_queryset(request).using(Conf.ORM)

    def has_add_permission(self, request):
        """Don't allow adds."""
        return False


admin.site.register(Schedule, ScheduleAdmin)
admin.site.register(Success, TaskAdmin)
admin.site.register(Failure, FailAdmin)

if Conf.ORM or Conf.TESTING:
    admin.site.register(OrmQ, QueueAdmin)
