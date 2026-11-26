from django.contrib import admin
from .models import CostomerFollowUp, LeadFollowUp, Task, TaskHistory

admin.site.register(Task)
admin.site.register(LeadFollowUp)
admin.site.register(CostomerFollowUp)
admin.site.register(TaskHistory)
