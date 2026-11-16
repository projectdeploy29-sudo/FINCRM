from django.contrib import admin
from .models import (
    Document,
    DocumentAccessLog,
    DocumentCategory,
)

admin.site.register(DocumentCategory)
admin.site.register(Document)
admin.site.register(DocumentAccessLog)