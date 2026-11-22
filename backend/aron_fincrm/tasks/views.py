from django.utils import timezone
from django.db.models import Q, Count, Sum
from django.db import transaction
from rest_framework import viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from organizations.tenant import get_user_organization, get_user_role_context
from permitions.permissions import IsAuthenticatedTenant, IsEmployee
from employes.models import Employee
from accounts.models import Manager, TeamLead
from tasks.models import Task, TaskHistory, CostomerFollowUp, LeadFollowUp, applicationFollowUp
from tasks.serializers import TaskSerializer, CustomerFollowUpSerializer, LeadFollowUpSerializer, ApplicationFollowUpSerializer
from applications.models import FinancialApplication
from leads.models import Lead
from customers.models import Customer
from finance.models import RepaymentSchedule, RepaymentPayment
from organizations.models import Department
from organizations.date_filters import apply_date_range
from organizations.dates import organization_day_bounds, organization_local_date

from rest_framework import serializers

class TaskHistorySerializer(serializers.ModelSerializer):
 class Meta:
  model=TaskHistory; fields=['id','previous_status','new_status','changed_by','comment','created_at']

def scope_followups(qs,model,user,request):
 ctx=get_user_role_context(user,request); level=ctx['hierarchy_level']
 if level>=90:return qs
 entity_owner={CostomerFollowUp:'customer__assigned_to',LeadFollowUp:'lead__assigned_to',applicationFollowUp:'application__assigned_employee'}[model]
 if level>=70:
  manager=user.manager_set.first() if hasattr(user,'manager_set') else None; depts=manager.managed_departments.all() if manager else []
  return qs.filter(Q(assigned_to__department__in=depts)|Q(**{entity_owner+'__department__in':depts})).distinct()
 if level>=50:
  profile=user.teamlead_profiles.first() if hasattr(user,'teamlead_profiles') else None; teams=profile.teams.all() if profile else []
  return qs.filter(Q(assigned_to__team__in=teams)|Q(**{entity_owner+'__team__in':teams})).distinct()
 employee=getattr(user,'employee',None)
 return qs.filter(assigned_to=employee).distinct() if employee else qs.none()

class TaskViewSet(viewsets.ModelViewSet):
 serializer_class=TaskSerializer; permission_classes=[IsAuthenticatedTenant]; filterset_fields=['priority','assigned_to','team','department']; search_fields=['title','description']; ordering_fields=['due_date','priority','created_at']; ordering=['due_date','id']
 def get_queryset(self):
  org=get_user_organization(self.request.user,self.request); qs=Task.objects.filter(organization=org) if org else Task.objects.none(); role=get_user_role_context(self.request.user,self.request); emp=getattr(self.request.user,'employee',None)
  level=role['hierarchy_level']; user=self.request.user
  if level<90:
   if level>=70:
    manager=user.manager_set.first() if hasattr(user,'manager_set') else None; departments=manager.managed_departments.all() if manager else []
    qs=qs.filter(Q(department__in=departments)|Q(assigned_to__department__in=departments)|Q(assigned_to_user=user)|Q(assigned_by_user=user))
   elif level>=50:
    profile=user.teamlead_profiles.first() if hasattr(user,'teamlead_profiles') else None; teams=profile.teams.all() if profile else []
    qs=qs.filter(Q(team__in=teams)|Q(assigned_to__team__in=teams)|Q(assigned_to_user=user)|Q(assigned_by_user=user))
   elif emp: qs=qs.filter(Q(assigned_to=emp)|Q(assigned_to_user=user)|Q(assigned_by_user=user))
   else: qs=qs.none()
  status_filter=self.request.query_params.get('status')
  if status_filter=='open': qs=qs.exclude(status__in=['COMPLETED','CANCELLED'])
  elif status_filter: qs=qs.filter(status=status_filter)
  if self.request.query_params.get('overdue')=='true': qs=qs.filter(due_date__lt=timezone.now()).exclude(status__in=['COMPLETED','CANCELLED'])
  return qs.select_related('assigned_to__user','related_customer','related_lead','related_application')
 @action(detail=False,methods=['get'],url_path='my-tasks')
 def my_tasks(self,request):
  ctx=get_user_role_context(request.user,request)
  if ctx['hierarchy_level']>=90:return Response([])
  emp=getattr(request.user,'employee',None); qs=self.get_queryset().filter(Q(assigned_to_user=request.user)|Q(assigned_to=emp)) if emp else self.get_queryset().filter(assigned_to_user=request.user); return Response(self.get_serializer(qs.order_by('due_date'),many=True).data)
 def get_permissions(self):
  if self.action=='create':return [IsAuthenticatedTenant(),IsEmployee()]
  return [IsAuthenticatedTenant()]
 @action(detail=True,methods=['post'])
 def transition(self,request,pk=None):
  task=self.get_object(); new=request.data.get('status'); allowed={'PENDING':{'IN_PROGRESS','CANCELLED'},'IN_PROGRESS':{'COMPLETED','CANCELLED','PENDING'},'COMPLETED':set(),'CANCELLED':set()}
  if new not in allowed.get(task.status,set()): return Response({'detail':'Invalid task status transition.'},status=400)
  old=task.status; task.status=new
  if new=='COMPLETED': task.completed_at=timezone.now()
  with transaction.atomic():
   task.save(); TaskHistory.objects.create(task=task,previous_status=old,new_status=new,changed_by=request.user,comment=request.data.get('comment',''))
  return Response(self.get_serializer(task).data)
 @action(detail=True,methods=['get'])
 def history(self,request,pk=None):
  task=self.get_object(); return Response(TaskHistorySerializer(task.history.select_related('changed_by').order_by('-created_at'),many=True).data)

class CustomerFollowUpViewSet(viewsets.ModelViewSet):
 serializer_class=CustomerFollowUpSerializer; permission_classes=[IsAuthenticatedTenant]; filterset_fields=['customer','assigned_to','status','followup_type']; search_fields=['title','description','purpose','notes','outcome','customer__full_name','customer__primary_phone']
 def get_queryset(self):
  org=get_user_organization(self.request.user,self.request); qs=CostomerFollowUp.objects.filter(organization=org) if org else CostomerFollowUp.objects.none()
  return scope_followups(qs,CostomerFollowUp,self.request.user,self.request).select_related('customer','created_by__user').order_by('-scheduled_at','pk')
class LeadFollowUpViewSet(viewsets.ModelViewSet):
 serializer_class=LeadFollowUpSerializer; permission_classes=[IsAuthenticatedTenant]; filterset_fields=['lead','assigned_to','status','followup_type']; search_fields=['title','description','purpose','notes','outcome','lead__contact_name','lead__lead_code']
 def get_queryset(self):
  org=get_user_organization(self.request.user,self.request); qs=LeadFollowUp.objects.filter(organization=org) if org else LeadFollowUp.objects.none()
  return scope_followups(qs,LeadFollowUp,self.request.user,self.request).select_related('lead','created_by__user').order_by('-scheduled_at','pk')
class ApplicationFollowUpViewSet(viewsets.ModelViewSet):
 serializer_class=ApplicationFollowUpSerializer; permission_classes=[IsAuthenticatedTenant]; filterset_fields=['application','assigned_to','status','followup_type']; search_fields=['title','description','purpose','notes','outcome','application__application_code','application__customer__full_name']
 def get_queryset(self):
  org=get_user_organization(self.request.user,self.request); qs=applicationFollowUp.objects.filter(organization=org) if org else applicationFollowUp.objects.none()
  return scope_followups(qs,applicationFollowUp,self.request.user,self.request).select_related('application__customer','application__lead','created_by__user').order_by('-scheduled_at','pk')

@api_view(['GET'])
@permission_classes([IsAuthenticatedTenant])
def followups_today(request):
 org=get_user_organization(request.user,request); day=organization_local_date(request); result=[]
 ctx=get_user_role_context(request.user,request); level=ctx['hierarchy_level']; user=request.user
 if level>=90:return Response([])
 for model,field,kind in [(CostomerFollowUp,'customer','customer'),(LeadFollowUp,'lead','lead'),(applicationFollowUp,'application','application')]:
  qs=model.objects.filter(organization=org,status='PENDING')
  qs=scope_followups(qs,model,user,request)
  if not request.query_params.get('start_date') and not request.query_params.get('end_date'):
   day_start, day_end=organization_day_bounds(day,request)
   qs=qs.filter(scheduled_at__gte=day_start,scheduled_at__lt=day_end)
  else:
   qs=apply_date_range(qs,request,'scheduled_at')
  if model is CostomerFollowUp: qs=qs.select_related('customer','assigned_to__user')
  elif model is LeadFollowUp: qs=qs.select_related('lead','assigned_to__user')
  else: qs=qs.select_related('application__customer','application__lead','assigned_to__user')
  for obj in qs.order_by('scheduled_at'):
   related=getattr(obj,field)
   customer=related.customer if model is applicationFollowUp else related if model is CostomerFollowUp else None
   contact_name=(getattr(related,'contact_name','') or getattr(customer,'full_name','') or getattr(customer,'legal_name','') or 'Customer')
   assigned_user=getattr(getattr(obj,'assigned_to',None),'user',None)
   result.append({'id':str(obj.pk),'kind':kind,'entity_id':str(getattr(obj,field+'_id')),'title':obj.title or obj.followup_type.title(),'description':obj.description,'purpose':obj.purpose,'contact_name':contact_name,'contact_phone':getattr(related,'phone','') or getattr(customer,'primary_phone','') or '', 'contact_email':getattr(related,'email','') or getattr(customer,'email','') or '', 'contact_record_code':getattr(related,'lead_code','') or getattr(related,'customer_code','') or getattr(related,'application_code','') or '', 'assigned_to_name':(assigned_user.get_full_name() or assigned_user.username) if assigned_user else '', 'scheduled_at':obj.scheduled_at,'followup_type':obj.followup_type,'notes':obj.notes})
 return Response(sorted(result,key=lambda item:item['scheduled_at']))

@api_view(['GET'])
@permission_classes([IsAuthenticatedTenant])
def task_recipients(request):
 ctx=get_user_role_context(request.user,request); level=ctx['hierarchy_level']; org=get_user_organization(request.user,request); rows=[]
 if not org or level<30:return Response(rows)
 if level<50:
  employee=getattr(request.user,'employee',None)
  employees=[employee] if employee and employee.organization_id==org.id else []
  managers=Manager.objects.none(); leads=TeamLead.objects.none()
 elif level>=90:
  employees=Employee.objects.filter(organization=org,employment_status='active').select_related('user')
  managers=Manager.objects.filter(organization=org,employment_status='active').select_related('user')
  leads=TeamLead.objects.filter(organization=org,user__isnull=False,employment_status='active').select_related('user')
 elif level>=70:
  manager=request.user.manager_set.first()
  depts=manager.managed_departments.all() if manager else []
  employees=Employee.objects.filter(organization=org,department__in=depts,employment_status='active').select_related('user')
  managers=Manager.objects.none()
  leads=TeamLead.objects.filter(organization=org,department__in=depts,user__isnull=False,employment_status='active').select_related('user')
 else:
  profile=request.user.teamlead_profiles.first()
  teams=profile.teams.all() if profile else []
  employees=Employee.objects.filter(organization=org,team__in=teams,employment_status='active').select_related('user')
  managers=Manager.objects.none(); leads=TeamLead.objects.none()
 rows += [{'id':str(row.user_id),'name':row.user.get_full_name() or row.user.username,'role':'Employee'} for row in employees]
 rows += [{'id':str(row.user_id),'name':row.user.get_full_name() or row.user.username,'role':'Manager'} for row in managers]
 rows += [{'id':str(row.user_id),'name':row.user.get_full_name() or row.user.username,'role':'Team Lead'} for row in leads]
 return Response(rows)

@api_view(['GET'])
@permission_classes([IsAuthenticatedTenant])
def dashboard(request, role):
 org=get_user_organization(request.user,request); ctx=get_user_role_context(request.user,request); level=ctx['hierarchy_level']; emp=getattr(request.user,'employee',None)
 if not org:return Response({'detail':'Organization not found.'},status=400)
 required={'admin':90,'manager':70,'teamlead':50,'employee':30,'departments':70,'tasks':30}.get(role)
 if required is None:return Response({'detail':'Unknown dashboard.'},status=404)
 if level<required:return Response({'detail':'You do not have access to this dashboard.'},status=403)
 apps=FinancialApplication.objects.filter(organization=org); leads=Lead.objects.filter(organization=org); tasks=Task.objects.filter(organization=org); customers=Customer.objects.filter(organization=org)
 payments=RepaymentPayment.objects.filter(organization=org)
 if level>=70 and level<90:
  profile=request.user.manager_set.first() if hasattr(request.user,'manager_set') else None
  depts=profile.managed_departments.all() if profile else []
  apps=apps.filter(assigned_employee__department__in=depts); leads=leads.filter(assigned_to__department__in=depts); tasks=tasks.filter(Q(department__in=depts)|Q(assigned_to__department__in=depts)|Q(assigned_to_user=request.user)); customers=customers.filter(assigned_to__department__in=depts)
  payments=payments.filter(repayment_schedule__application__assigned_employee__department__in=depts)
 elif level>=50 and level<70:
  profile=request.user.teamlead_profiles.first() if hasattr(request.user,'teamlead_profiles') else None
  teams=profile.teams.all() if profile else []
  apps=apps.filter(assigned_employee__team__in=teams); leads=leads.filter(assigned_to__team__in=teams); tasks=tasks.filter(Q(team__in=teams)|Q(assigned_to__team__in=teams)|Q(assigned_to_user=request.user)); customers=customers.filter(assigned_to__team__in=teams)
  payments=payments.filter(repayment_schedule__application__assigned_employee__team__in=teams)
 elif emp:
  apps=apps.filter(assigned_employee=emp); leads=leads.filter(assigned_to=emp); tasks=tasks.filter(assigned_to=emp); customers=customers.filter(assigned_to=emp)
  payments=payments.filter(Q(recorded_by=emp)|Q(repayment_schedule__application__assigned_employee=emp))
 apps=apply_date_range(apps,request,'created_at')
 leads=apply_date_range(leads,request,'created_at')
 tasks=apply_date_range(tasks,request,'due_date')
 customers=apply_date_range(customers,request,'created_at')
 payments=apply_date_range(payments,request,'payment_date')
 status_rows=list(apps.values('status').annotate(count=Count('id')))
 lead_count=leads.count(); converted=leads.filter(status='qualified').count()
 completion_total=tasks.exclude(status='CANCELLED').count(); completion_rate=round(tasks.filter(status='COMPLETED').count()*100/completion_total,2) if completion_total else 0
 day=organization_local_date(request)
 schedules=RepaymentSchedule.objects.filter(organization=org,due_date__lt=day,status__in=['PENDING','PARTIAL'])
 if 70<=level<90:
  manager=request.user.manager_set.first() if hasattr(request.user,'manager_set') else None
  depts=manager.managed_departments.all() if manager else []
  schedules=schedules.filter(application__assigned_employee__department__in=depts)
 elif 50<=level<70:
  profile=request.user.teamlead_profiles.first() if hasattr(request.user,'teamlead_profiles') else None
  teams=profile.teams.all() if profile else []
  schedules=schedules.filter(application__assigned_employee__team__in=teams)
 elif level<50 and emp:
  schedules=schedules.filter(application__assigned_employee=emp)
 elif level<50:
  schedules=schedules.none()
 schedules=apply_date_range(schedules,request,'due_date')
 team_performance=list(tasks.values('assigned_to__team__id','assigned_to__team__name').annotate(total_tasks=Count('id'),completed_tasks=Count('id',filter=Q(status='COMPLETED'))).order_by('assigned_to__team__name')) if role in ('manager','teamlead','admin') else []
 departments=Department.objects.filter(organization=org)
 if role=='departments' and level<90:
  manager=request.user.manager_set.first() if hasattr(request.user,'manager_set') else None
  departments=departments.filter(pk__in=manager.managed_departments.values('id')) if manager else departments.none()
 department_performance=[{'id':str(department.id),'name':department.name,'teams':department.team_set.count(),'employees':department.employee_set.count(),'applications':apps.filter(assigned_employee__department=department).count(),'tasks':tasks.filter(department=department).count()} for department in departments]
 data={'role':role,'customers':customers.count(),'leads':lead_count,'leads_converted':converted,'conversion_rate':round(converted*100/lead_count,2) if lead_count else 0,'applications':apps.count(),'applications_approved':apps.filter(status='approved').count(),'applications_rejected':apps.filter(status='rejected').count(),'applications_pending':apps.filter(status__in=['draft','submitted','under_review']).count(),'application_status':status_rows,'tasks_open':tasks.exclude(status__in=['COMPLETED','CANCELLED']).count(),'tasks_completed':tasks.filter(status='COMPLETED').count(),'tasks_overdue':tasks.filter(due_date__lt=timezone.now()).exclude(status__in=['COMPLETED','CANCELLED']).count(),'task_completion_rate':completion_rate,'team_performance':team_performance,'department_performance':department_performance if role in ('departments','admin') else [],'payments_recorded':payments.count(),'verified_revenue':payments.filter(verification_status='VERIFIED').aggregate(total=Sum('amount'))['total'] or 0,'pending_payments':payments.filter(verification_status='PENDING').count(),'overdue_installments':schedules.count(),'overdue_expected_amount':schedules.aggregate(total=Sum('expected_amount'))['total'] or 0,'disbursed_amount':apps.filter(status='disbursed').aggregate(total=Sum('disbursed_amount'))['total'] or 0}
 return Response(data)

# Create your views here.
