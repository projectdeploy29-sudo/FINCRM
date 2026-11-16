from django.contrib import admin
from .models import Employee, EmployeeAssignmentHistory

admin.site.register(Employee)

admin.site.register(EmployeeAssignmentHistory)