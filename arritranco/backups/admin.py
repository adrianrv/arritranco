'''
Created on 25/12/2010

@author:  rmrodri
'''
from django.contrib import admin
from models import FileBackupTask, FileNamePattern, FileBackupProduct, BackupFile

class FileBackupTaskAdmin(admin.ModelAdmin):
    list_display = ('machine', 'duration', 'bckp_type', 'checker_fqdn', 'directory', 'days_in_hard_drive', 'max_backup_month')
    list_filter = ('bckp_type', 'checker_fqdn')
    list_editable = ('bckp_type', )

class FileBackupProductAdmin(admin.ModelAdmin):
    list_display = ('file_backup_task', 'file_pattern', 'task', 'variable_percentage')

admin.site.register(FileBackupTask, FileBackupTaskAdmin)
admin.site.register(FileNamePattern)
admin.site.register(FileBackupProduct, FileBackupProductAdmin)
admin.site.register(BackupFile)
