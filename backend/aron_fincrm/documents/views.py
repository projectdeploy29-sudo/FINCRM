from rest_framework import viewsets
from rest_framework.decorators import action
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.db.models import Q
from organizations.tenant import get_user_organization, get_user_role_context
from permitions.permissions import IsAuthenticatedTenant, IsEmployee, IsOrgAdmin, IsManager
from documents.models import Document, DocumentCategory, DocumentAccessLog
from documents.serializers import DocumentSerializer, DocumentCategorySerializer

class DocumentCategoryViewSet(viewsets.ModelViewSet):
 serializer_class=DocumentCategorySerializer; permission_classes=[IsAuthenticatedTenant]
 def get_permissions(self):
  if self.action in ('create','update','partial_update'):return [IsAuthenticatedTenant(),IsManager()]
  if self.action=='destroy':return [IsAuthenticatedTenant(),IsOrgAdmin()]
  return [IsAuthenticatedTenant()]
 def get_queryset(self):
  org=get_user_organization(self.request.user,self.request); qs=DocumentCategory.objects.filter(organization=org) if org else DocumentCategory.objects.none()
  return qs
class DocumentViewSet(viewsets.ModelViewSet):
 serializer_class=DocumentSerializer; permission_classes=[IsAuthenticatedTenant]; filterset_fields=['application','customer','category','status']
 def get_permissions(self):
  if self.action in ('update','partial_update'): return [IsAuthenticatedTenant(),IsEmployee()]
  if self.action=='destroy': return [IsAuthenticatedTenant(),IsOrgAdmin()]
  if self.action=='create': return [IsAuthenticatedTenant(),IsEmployee()]
  return [IsAuthenticatedTenant()]
 def get_queryset(self):
  org=get_user_organization(self.request.user,self.request)
  if not org:return Document.objects.none()
  qs=Document.objects.filter(organization=org).select_related('category','customer','application')
  from organizations.tenant import get_user_role_context
  ctx=get_user_role_context(self.request.user,self.request); level=ctx['hierarchy_level']; user=self.request.user
  if level>=90:return qs
  if level>=70:
   manager=user.manager_set.first() if hasattr(user,'manager_set') else None
   departments=manager.managed_departments.all() if manager else []
   return qs.filter(application__assigned_employee__department__in=departments)
  if level>=50:
   profile=user.teamlead_profiles.first() if hasattr(user,'teamlead_profiles') else None
   teams=profile.teams.all() if profile else []
   return qs.filter(application__assigned_employee__team__in=teams)
  employee=getattr(user,'employee',None)
  return qs.filter(Q(application__assigned_employee=employee)|Q(customer__assigned_to=employee)).distinct() if employee else qs.none()
 def perform_create(self,serializer):
  doc=serializer.save(); self._audit(doc,DocumentAccessLog.Action.UPLOAD)
 def perform_update(self,serializer):
  doc=serializer.save()
  if 'file' in serializer.validated_data:self._audit(doc,DocumentAccessLog.Action.REPLACE)
 def retrieve(self,request,*args,**kwargs):
  response=super().retrieve(request,*args,**kwargs); self._audit(self.get_object(),DocumentAccessLog.Action.VIEW); return response
 @action(detail=True,methods=['get'])
 def download(self,request,pk=None):
  document=self.get_object(); self._audit(document,DocumentAccessLog.Action.DOWNLOAD)
  return FileResponse(document.file.open('rb'),as_attachment=True,filename=document.file_name or 'document')
 @action(detail=True,methods=['post'])
 def review(self,request,pk=None):
  if not IsEmployee().has_permission(request,self):
   from rest_framework.response import Response
   return Response({'detail':'A staff member assigned to this record is required.'},status=403)
  document=self.get_object(); decision=request.data.get('status')
  if decision not in (Document.Status.ACCEPTED,Document.Status.REJECTED):
   from rest_framework.response import Response
   return Response({'detail':'Status must be accepted or rejected.'},status=400)
  document.status=decision; document.save(update_fields=['status'])
  if document.application_id:
   from applications.models import ApplicationChecklist
   ApplicationChecklist.objects.update_or_create(
    application=document.application,document=document,
    defaults={'status':ApplicationChecklist.Status.ACCEPTED if decision==Document.Status.ACCEPTED else ApplicationChecklist.Status.REJECTED,'remarks':request.data.get('remarks',''),'updated_by':request.user},
   )
  self._audit(document,DocumentAccessLog.Action.VERIFY)
  from rest_framework.response import Response
  return Response(DocumentSerializer(document,context={'request':request}).data)
 def _audit(self,doc,action):
  ctx=get_user_role_context(self.request.user,self.request)
  from permitions.models import Role
  role=Role.objects.filter(code=ctx['role_code']).filter(Q(organization=doc.organization)|Q(organization__isnull=True)).first()
  if role: DocumentAccessLog.objects.create(document=doc,role=role,action=action,ip_address=self.request.META.get('REMOTE_ADDR'))

# Create your views here.
