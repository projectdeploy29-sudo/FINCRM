from rest_framework import serializers
from django.utils import timezone
from tasks.models import Task, TaskHistory, CostomerFollowUp, LeadFollowUp, applicationFollowUp
from organizations.tenant import get_user_organization, get_user_role_context

class TaskSerializer(serializers.ModelSerializer):
 class Meta: model=Task; fields='__all__'; read_only_fields=('organization','assigned_by_user','assigned_by_manager','assigned_by_teamlead','status','completed_at','created_at','updated_at')
 def validate(self,attrs):
  req=self.context['request']; org=get_user_organization(req.user,req); instance=self.instance
  for field in ('assigned_to','department','team','related_customer','related_lead','related_application'):
   related=attrs.get(field,getattr(instance,field,None))
   if related and getattr(related,'organization_id',None)!=getattr(org,'id',None): raise serializers.ValidationError({field:'This record must belong to your organization.'})
  assigned=attrs.get('assigned_to',getattr(instance,'assigned_to',None)); recipient=attrs.get('assigned_to_user',getattr(instance,'assigned_to_user',None)); employee=getattr(req.user,'employee',None); level=get_user_role_context(req.user,req)['hierarchy_level']
  manager=req.user.manager_set.first() if level>=70 and hasattr(req.user,'manager_set') else None
  profile=req.user.teamlead_profiles.first() if 50<=level<70 and hasattr(req.user,'teamlead_profiles') else None
  for field in ('related_customer','related_lead','related_application'):
   target=attrs.get(field,getattr(instance,field,None))
   if not target: continue
   owner=(target.assigned_to_id if field!='related_application' else target.assigned_employee_id)
   if level<50 and (not employee or owner!=employee.id): raise serializers.ValidationError({field:'Related records must be assigned to you.'})
   if 50<=level<70 and (not profile or not profile.teams.filter(pk=(target.team_id if field=='related_lead' else target.assigned_to.team_id if field=='related_customer' and target.assigned_to_id else target.assigned_employee.team_id if field=='related_application' and target.assigned_employee_id else None)).exists()): raise serializers.ValidationError({field:'Related records must belong to a team you lead.'})
   if 70<=level<90 and (not manager or not manager.managed_departments.filter(pk=(target.department_id if field=='related_lead' else target.assigned_to.department_id if field=='related_customer' and target.assigned_to_id else target.assigned_employee.department_id if field=='related_application' and target.assigned_employee_id else None)).exists()): raise serializers.ValidationError({field:'Related records must belong to a department you manage.'})
  if not assigned and not recipient: raise serializers.ValidationError({'assigned_to_user':'Choose a task recipient.'})
  if assigned and recipient and assigned.user_id != recipient.id: raise serializers.ValidationError({'assigned_to_user':'Recipient must match the selected employee.'})
  team=attrs.get('team',getattr(instance,'team',None)); department=attrs.get('department',getattr(instance,'department',None))
  if assigned and team and assigned.team_id!=team.id: raise serializers.ValidationError({'team':'Task team must match the assigned employee team.'})
  if assigned and department and assigned.department_id!=department.id: raise serializers.ValidationError({'department':'Task department must match the assigned employee department.'})
  if level<50 and (not employee or (assigned and assigned.id!=employee.id) or (recipient and recipient.id!=req.user.id)): raise serializers.ValidationError({'assigned_to_user':'Employees may only create tasks for themselves.'})
  if assigned and 70<=level<90:
   manager=req.user.manager_set.first() if hasattr(req.user,'manager_set') else None
   if not manager or not manager.managed_departments.filter(pk=assigned.department_id).exists(): raise serializers.ValidationError({'assigned_to':'Employee must belong to a department you manage.'})
  elif assigned and 50<=level<70:
   profile=req.user.teamlead_profiles.first() if hasattr(req.user,'teamlead_profiles') else None
   if not profile or not profile.teams.filter(pk=assigned.team_id).exists(): raise serializers.ValidationError({'assigned_to':'Employee must belong to a team you lead.'})
  if recipient:
   from accounts.models import Manager, TeamLead
   from employes.models import Employee
   target_employee=Employee.objects.filter(user=recipient,organization=org).first()
   target_manager=Manager.objects.filter(user=recipient,organization=org).first()
   target_lead=TeamLead.objects.filter(user=recipient,organization=org).first()
   if not (target_employee or target_manager or target_lead): raise serializers.ValidationError({'assigned_to_user':'Recipient must be an active staff member in your organization.'})
   if level>=90: pass
   elif level>=70:
    manager=req.user.manager_set.first()
    depts=manager.managed_departments.all() if manager else []
    if target_manager or not (target_employee and target_employee.department_id in set(depts.values_list('id',flat=True)) or target_lead and depts.filter(pk=target_lead.department_id).exists()): raise serializers.ValidationError({'assigned_to_user':'Choose a team lead or employee in a department you manage.'})
   elif level>=50:
    profile=req.user.teamlead_profiles.first()
    teams=profile.teams.all() if profile else []
    if not target_employee or not teams.filter(pk=target_employee.team_id).exists(): raise serializers.ValidationError({'assigned_to_user':'Choose an employee in a team you lead.'})
   if target_employee and not assigned: attrs['assigned_to']=target_employee
  return attrs
 def create(self,data):
  req=self.context['request']; org=get_user_organization(req.user,req); emp=getattr(req.user,'employee',None)
  assigned=data.get('assigned_to')
  if assigned:
   data.setdefault('team',assigned.team)
   data.setdefault('department',assigned.department)
   data.setdefault('assigned_to_user',assigned.user)
  ctx=get_user_role_context(req.user,req); manager=getattr(req.user,'manager_set',None); manager=manager.first() if manager and manager.exists() else None
  teamlead=getattr(req.user,'teamlead_profiles',None); teamlead=teamlead.first() if teamlead and teamlead.exists() else None
  if ctx['hierarchy_level']>=70 and manager: data['assigned_by_manager']=manager
  if ctx['hierarchy_level']==50 and teamlead: data['assigned_by_teamlead']=teamlead
  from django.db import transaction
  with transaction.atomic():
   task=super().create({**data,'organization':org,'assigned_by_user':req.user})
   TaskHistory.objects.create(task=task,previous_status=task.status,new_status=task.status,changed_by=req.user,comment='Task created')
   return task
class CustomerFollowUpSerializer(serializers.ModelSerializer):
 title=serializers.CharField(required=True,allow_blank=False)
 contact_name=serializers.SerializerMethodField()
 contact_phone=serializers.SerializerMethodField()
 contact_email=serializers.SerializerMethodField()
 contact_record_code=serializers.SerializerMethodField()
 created_by_name=serializers.SerializerMethodField()
 assigned_to_name=serializers.SerializerMethodField()
 class Meta: model=CostomerFollowUp; fields='__all__'; read_only_fields=('organization','created_by','created_by_user','created_at','updated_at','completed_at')
 def _related_record(self,obj):
  if self.Meta.model is CostomerFollowUp: return obj.customer
  if self.Meta.model is LeadFollowUp: return obj.lead
  return obj.application
 def _contact_customer(self,obj):
  record=self._related_record(obj)
  if self.Meta.model is applicationFollowUp: return getattr(record,'customer',None)
  return record if self.Meta.model is CostomerFollowUp else None
 def get_contact_name(self,obj):
  record=self._related_record(obj); customer=self._contact_customer(obj)
  return (getattr(record,'contact_name','') or getattr(customer,'full_name','') or getattr(customer,'legal_name','') or 'Customer')
 def get_contact_phone(self,obj):
  record=self._related_record(obj); customer=self._contact_customer(obj)
  return getattr(record,'phone','') or getattr(customer,'primary_phone','') or ''
 def get_contact_email(self,obj):
  record=self._related_record(obj); customer=self._contact_customer(obj)
  return getattr(record,'email','') or getattr(customer,'email','') or ''
 def get_contact_record_code(self,obj):
  record=self._related_record(obj)
  return getattr(record,'lead_code','') or getattr(record,'customer_code','') or getattr(record,'application_code','') or ''
 def get_created_by_name(self,obj):
  user=getattr(getattr(obj,'created_by',None),'user',None) or getattr(obj,'created_by_user',None)
  return (user.get_full_name() or user.username) if user else ''
 def get_assigned_to_name(self,obj):
  user=getattr(getattr(obj,'assigned_to',None),'user',None)
  return (user.get_full_name() or user.username) if user else ''
 def validate(self,attrs):
  req=self.context['request']; org=get_user_organization(req.user,req); instance=self.instance
  relation_name='customer' if self.Meta.model is CostomerFollowUp else 'lead' if self.Meta.model is LeadFollowUp else 'application'
  target=attrs.get(relation_name,getattr(instance,relation_name,None))
  if not org or not target or target.organization_id!=org.id: raise serializers.ValidationError({relation_name:'Choose a record in your organization.'})
  role=get_user_role_context(req.user,req); level=role['hierarchy_level']; employee=getattr(req.user,'employee',None)
  if level<30: raise serializers.ValidationError('Only organization staff can create or update internal follow-ups.')
  assigned=attrs.get('assigned_to',getattr(instance,'assigned_to',None))
  if not assigned and not instance and employee: assigned=employee; attrs['assigned_to']=employee
  if not assigned: raise serializers.ValidationError({'assigned_to':'Assign this follow-up to an employee.'})
  if assigned.organization_id!=org.id: raise serializers.ValidationError({'assigned_to':'Employee must belong to your organization.'})
  owner_field={CostomerFollowUp:'assigned_to',LeadFollowUp:'assigned_to',applicationFollowUp:'assigned_employee'}[self.Meta.model]
  owner=getattr(target,owner_field,None)
  if level<50 and (not employee or assigned!=employee or (not instance and owner!=employee)):
   raise serializers.ValidationError({relation_name:'Employees can only manage follow-ups for their own assigned records.'})
  if 50<=level<70:
   profile=req.user.teamlead_profiles.first() if hasattr(req.user,'teamlead_profiles') else None
   if not profile or not profile.teams.filter(pk=getattr(getattr(owner,'team',None),'id',None)).exists() or not profile.teams.filter(pk=assigned.team_id).exists(): raise serializers.ValidationError({'assigned_to':'Record and assigned employee must be in a team you lead.'})
  if 70<=level<90:
   manager=req.user.manager_set.first() if hasattr(req.user,'manager_set') else None
   if not manager or not manager.managed_departments.filter(pk=getattr(getattr(owner,'department',None),'id',None)).exists() or not manager.managed_departments.filter(pk=assigned.department_id).exists(): raise serializers.ValidationError({'assigned_to':'Record and assigned employee must be in a department you manage.'})
  duration=attrs.get('meeting_duration_minutes',getattr(instance,'meeting_duration_minutes',30))
  if duration < 1 or duration > 720: raise serializers.ValidationError({'meeting_duration_minutes':'Meeting duration must be between 1 and 720 minutes.'})
  raw_emails=attrs.get('invitee_emails',getattr(instance,'invitee_emails',''))
  email_field=serializers.EmailField()
  for email in filter(None,(item.strip() for item in raw_emails.split(','))):
   try: email_field.run_validation(email)
   except serializers.ValidationError: raise serializers.ValidationError({'invitee_emails':f'Invalid invitee email: {email}'})
  new_status=attrs.get('status',getattr(instance,'status',None))
  if instance and new_status!=instance.status and (instance.status!='PENDING' or new_status not in ('COMPLETED','CANCELLED')):
   raise serializers.ValidationError({'status':'Follow-ups can only move from pending to completed or cancelled.'})
  return attrs
 def update(self,instance,data):
  if data.get('status') in ('COMPLETED','CANCELLED') and instance.status=='PENDING':data['completed_at']=timezone.now()
  return super().update(instance,data)
 def create(self,data):
  req=self.context['request']; emp=getattr(req.user,'employee',None)
  data.setdefault('assigned_to',emp)
  return super().create({**data,'organization':get_user_organization(req.user,req),'created_by':emp,'created_by_user':req.user})
class LeadFollowUpSerializer(CustomerFollowUpSerializer):
 class Meta(CustomerFollowUpSerializer.Meta): model=LeadFollowUp
class ApplicationFollowUpSerializer(CustomerFollowUpSerializer):
 class Meta(CustomerFollowUpSerializer.Meta): model=applicationFollowUp
