from django.db import models


class UISyncRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = 'running', 'Running'
        SUCCEEDED = 'succeeded', 'Succeeded'
        PARTIAL = 'partial', 'Completed with warnings'
        FAILED = 'failed', 'Failed'

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RUNNING)
    source_root = models.CharField(max_length=500)
    full_sync = models.BooleanField(default=False)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    counts = models.JSONField(default=dict, blank=True)
    warning = models.TextField(blank=True)
    error = models.TextField(blank=True)

    class Meta:
        db_table = 'ui_knowledge_sync_run'
        ordering = ['-started_at']


class UIPage(models.Model):
    key = models.SlugField(max_length=180, unique=True)
    title = models.CharField(max_length=200)
    nav_label = models.CharField(max_length=200, blank=True)
    nav_parent = models.CharField(max_length=150, blank=True)
    frontend_route = models.CharField(max_length=255, blank=True)
    module_id = models.CharField(max_length=100, blank=True, db_index=True)
    source_path = models.CharField(max_length=500)
    minimum_role_level = models.PositiveSmallIntegerField(default=0)
    allowed_role_codes = models.JSONField(default=list, blank=True)
    required_permissions = models.JSONField(default=list, blank=True)
    source_hash = models.CharField(max_length=64, db_index=True)
    is_active = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ui_knowledge_page'
        ordering = ['title']

    def __str__(self):
        return self.title


class UIComponent(models.Model):
    key = models.SlugField(max_length=220, unique=True)
    name = models.CharField(max_length=200)
    component_type = models.CharField(max_length=40, default='component')
    source_path = models.CharField(max_length=500)
    source_hash = models.CharField(max_length=64, db_index=True)
    source_evidence = models.JSONField(default=dict, blank=True)
    pages = models.ManyToManyField(UIPage, related_name='components', blank=True)
    related_components = models.ManyToManyField('self', symmetrical=False, blank=True, related_name='used_by')
    is_active = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ui_knowledge_component'
        ordering = ['name']

    def __str__(self):
        return self.name


class UIFeature(models.Model):
    class ComponentType(models.TextChoices):
        NAVIGATION = 'navigation', 'Navigation'
        BUTTON = 'button', 'Button'
        FORM = 'form', 'Form'
        TABLE_ACTION = 'table_action', 'Table action'
        TAB = 'tab', 'Tab'
        DROPDOWN = 'dropdown', 'Dropdown'
        PAGE = 'page', 'Page'
        OTHER = 'other', 'Other'

    page = models.ForeignKey(UIPage, on_delete=models.CASCADE, related_name='features')
    component = models.ForeignKey(UIComponent, on_delete=models.CASCADE, related_name='features')
    feature_key = models.SlugField(max_length=220)
    name = models.CharField(max_length=220)
    component_type = models.CharField(max_length=24, choices=ComponentType.choices)
    purpose = models.TextField(blank=True)
    location = models.CharField(max_length=300, blank=True)
    workflow = models.JSONField(default=list, blank=True)
    evidence = models.JSONField(default=dict, blank=True)
    minimum_role_level = models.PositiveSmallIntegerField(default=0)
    allowed_role_codes = models.JSONField(default=list, blank=True)
    required_permissions = models.JSONField(default=list, blank=True)
    source_hash = models.CharField(max_length=64, db_index=True)
    documentation_version = models.PositiveIntegerField(default=1)
    is_verified = models.BooleanField(default=False)
    requires_verification = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ui_knowledge_feature'
        constraints = [models.UniqueConstraint(fields=['page', 'feature_key'], name='uniq_ui_feature_page_key')]
        ordering = ['page__title', 'name']

    def __str__(self):
        return f'{self.page.title}: {self.name}'


class UINavigationItem(models.Model):
    key = models.SlugField(max_length=220, unique=True)
    label = models.CharField(max_length=200)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    page = models.ForeignKey(UIPage, on_delete=models.SET_NULL, null=True, blank=True, related_name='navigation_items')
    module_id = models.CharField(max_length=100, blank=True)
    minimum_role_level = models.PositiveSmallIntegerField(default=0)
    allowed_role_codes = models.JSONField(default=list, blank=True)
    required_permissions = models.JSONField(default=list, blank=True)
    source_path = models.CharField(max_length=500)
    source_hash = models.CharField(max_length=64, db_index=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'ui_knowledge_navigation'
        ordering = ['parent_id', 'label']

    def __str__(self):
        return self.label
