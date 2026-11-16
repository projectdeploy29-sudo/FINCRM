import uuid

from django.db import models


class Role(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.organizations_organization",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=100)
    code = models.SlugField(max_length=100)
    description = models.TextField(blank=True)
    is_system_role = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "permissions_role"


class Permission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    module = models.CharField(max_length=100)
    action = models.CharField(max_length=50)
    codename = models.SlugField(max_length=150, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "permissions_permission"


class RolePermission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.ForeignKey("permitions.Role", on_delete=models.CASCADE)
    permission = models.ForeignKey("permitions.Permission", on_delete=models.CASCADE)

    class Meta:
        db_table = "permissions_rolepermission"


