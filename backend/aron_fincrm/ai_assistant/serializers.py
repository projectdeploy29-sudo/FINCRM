from rest_framework import serializers


class AssistantChatSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=2000, trim_whitespace=True)
    history = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        max_length=8,
    )

    def validate_history(self, history):
        safe_history = []
        for item in history:
            role = item.get('role')
            content = item.get('content')
            if role not in ('user', 'assistant') or not isinstance(content, str):
                raise serializers.ValidationError('History entries need a user or assistant role and text content.')
            content = content.strip()
            if content:
                safe_history.append({'role': role, 'content': content[:3000]})
        return safe_history
