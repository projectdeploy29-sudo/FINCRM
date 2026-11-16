from django.contrib import admin
from .models import Interaction, InteractionAttendee, MessageDraft

admin.site.register(Interaction)
admin.site.register(InteractionAttendee)
admin.site.register(MessageDraft)