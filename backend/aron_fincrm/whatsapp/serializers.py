from rest_framework import serializers

from .models import WhatsAppMessage, WhatsAppMessageTemplate


class WhatsAppMessageTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = WhatsAppMessageTemplate
        fields = ['id', 'title', 'body']


class PrepareFollowupWhatsAppSerializer(serializers.Serializer):
    followup_kind = serializers.ChoiceField(choices=WhatsAppMessage.FollowupKind.choices)
    followup_id = serializers.CharField(max_length=64)
    template_id = serializers.IntegerField(required=False)
    custom_message = serializers.CharField(max_length=1200, required=False, allow_blank=True, trim_whitespace=True)

    def validate(self, attrs):
        has_template = attrs.get('template_id') is not None
        custom_message = attrs.get('custom_message', '').strip()
        if has_template == bool(custom_message):
            raise serializers.ValidationError('Choose one saved message or enter a custom message.')
        attrs['custom_message'] = custom_message
        return attrs


class WhatsAppMessageHistorySerializer(serializers.ModelSerializer):
    template_title = serializers.CharField(source='source_template.title', read_only=True, default='')
    sent_by_name = serializers.SerializerMethodField()

    class Meta:
        model = WhatsAppMessage
        fields = [
            'id', 'recipient_name', 'recipient_phone', 'message_body', 'status',
            'provider_message_id', 'error_detail', 'template_title', 'sent_by_name',
            'created_at', 'sent_at',
        ]

    def get_sent_by_name(self, instance):
        user = instance.sent_by
        return (user.get_full_name() or user.username) if user else ''