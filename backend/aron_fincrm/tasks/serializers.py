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
  assigned=attrs.get('assigned_to',getattr(instance,'assigned_to',None)); employee=getattr(req.user,'employee',None); level=get_user_role_context(req.user,req)['hierarchy_level']
  team=attrs.get('team',getattr(instance,'team',None)); department=attrs.get('department',getattr(instance,'department',None))
  if assigned and team and assigned.team_id!=team.id: raise serializers.ValidationError({'team':'Task team must match the assigned employee team.'})
  if assigned and department and assigned.department_id!=department.id: raise serializers.ValidationError({'department':'Task department must match the assigned employee department.'})
  if level<50 and (not employee or not assigned or assigned.id!=employee.id): raise serializers.ValidationError({'assigned_to':'Employees may only create tasks for themselves.'})
  if assigned and 70<=level<90:
   manager=req.user.manager_set.first() if hasattr(req.user,'manager_set') else None
   if not manager or not manager.managed_departments.filter(pk=assigned.department_id).exists(): raise serializers.ValidationError({'assigned_to':'Employee must belong to a department you manage.'})
  elif assigned and 50<=level<70:
   profile=req.user.teamlead_profiles.first() if hasattr(req.user,'teamlead_profiles') else None
   if not profile or not profile.teams.filter(pk=assigned.team_id).exists(): raise serializers.ValidationError({'assigned_to':'Employee must belong to a team you lead.'})
  return attrs
 def create(self,data):
  req=self.context['request']; org=get_user_organization(req.user,req); emp=getattr(req.user,'employee',None)
  assigned=data.get('assigned_to')
  if assigned:
   data.setdefault('team',assigned.team)
   data.setdefault('department',assigned.department)
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
 class Meta: model=CostomerFollowUp; fields='__all__'; read_only_fields=('organization','created_by','created_at','updated_at','completed_at')
 def validate(self,attrs):
  req=self.context['request']; org=get_user_organization(req.user,req); instance=self.instance
  relation_name='customer' if self.Meta.model is CostomerFollowUp else 'lead' if self.Meta.model is LeadFollowUp else 'application'
  target=attrs.get(relation_name,getattr(instance,relation_name,None))
  if not org or not target or target.organization_id!=org.id: raise serializers.ValidationError({relation_name:'Choose a record in your organization.'})
  if not getattr(req.user,'employee',None): raise serializers.ValidationError('An employee profile is required to create follow-ups.')
  new_status=attrs.get('status',getattr(instance,'status',None))
  if instance and new_status!=instance.status and (instance.status!='PENDING' or new_status not in ('COMPLETED','CANCELLED')):
   raise serializers.ValidationError({'status':'Follow-ups can only move from pending to completed or cancelled.'})
  return attrs
 def update(self,instance,data):
  if data.get('status') in ('COMPLETED','CANCELLED') and instance.status=='PENDING':data['completed_at']=timezone.now()
  return super().update(instance,data)
 def create(self,data):
  req=self.context['request']; emp=getattr(req.user,'employee',None)
  if not emp: raise serializers.ValidationError('Employee profile required.')
  return super().create({**data,'organization':get_user_organization(req.user,req),'created_by':emp})
class LeadFollowUpSerializer(CustomerFollowUpSerializer):
 class Meta(CustomerFollowUpSerializer.Meta): model=LeadFollowUp
class ApplicationFollowUpSerializer(CustomerFollowUpSerializer):
 class Meta(CustomerFollowUpSerializer.Meta): model=applicationFollowUp
