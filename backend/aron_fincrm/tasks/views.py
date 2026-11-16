from django.utils import timezone
from django.db.models import Q, Count, Sum
from django.db import transaction
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from organizations.tenant import get_user_organization, get_user_role_context
from permitions.permissions import IsAuthenticatedTenant
from tasks.models import Task, TaskHistory, CostomerFollowUp, LeadFollowUp, applicationFollowUp
from tasks.serializers import TaskSerializer, CustomerFollowUpSerializer, LeadFollowUpSerializer, ApplicationFollowUpSerializer
from applications.models import FinancialApplication
from leads.models import Lead
from customers.models import Customer
from finance.models import RepaymentSchedule, RepaymentPayment
from documents.models import Document
from organizations.models import Department, Team

from rest_framework import serializers

class TaskHistorySerializer(serializers.ModelSerializer):
 class Meta:
  model=TaskHistory; fields=['id','previous_status','new_status','changed_by','comment','created_at']

def scope_followups(qs,model,user,request):
 ctx=get_user_role_context(user,request); level=ctx['hierarchy_level']
 if level>=90:return qs
 if level>=70:
  manager=user.manager_set.first() if hasattr(user,'manager_set') else None; depts=manager.managed_departments.all() if manager else []
  field={CostomerFollowUp:'customer__created_by__department',LeadFollowUp:'lead__assigned_to__department',applicationFollowUp:'application__assigned_employee__department'}[model]
  return qs.filter(**{field+'__in':depts})
 if level>=50:
  profile=user.teamlead_profiles.first() if hasattr(user,'teamlead_profiles') else None; teams=profile.teams.all() if profile else []
  field={CostomerFollowUp:'customer__created_by__team',LeadFollowUp:'lead__assigned_to__team',applicationFollowUp:'application__assigned_employee__team'}[model]
  return qs.filter(**{field+'__in':teams})
 return qs.filter(created_by=getattr(user,'employee',None))

class TaskViewSet(viewsets.ModelViewSet):
 serializer_class=TaskSerializer; permission_classes=[IsAuthenticatedTenant]; filterset_fields=['priority','assigned_to','team','department']; search_fields=['title','description']; ordering_fields=['due_date','priority','created_at']
 def get_queryset(self):
  org=get_user_organization(self.request.user,self.request); qs=Task.objects.filter(organization=org) if org else Task.objects.none(); role=get_user_role_context(self.request.user,self.request); emp=getattr(self.request.user,'employee',None)
  level=role['hierarchy_level']; user=self.request.user
  if level<90:
   if level>=70:
    manager=user.manager_set.first() if hasattr(user,'manager_set') else None; departments=manager.managed_departments.all() if manager else []
    qs=qs.filter(Q(department__in=departments)|Q(assigned_to__department__in=departments)|Q(assigned_by_user=user))
   elif level>=50:
    profile=user.teamlead_profiles.first() if hasattr(user,'teamlead_profiles') else None; teams=profile.teams.all() if profile else []
    qs=qs.filter(Q(team__in=teams)|Q(assigned_to__team__in=teams)|Q(assigned_by_user=user))
   elif emp: qs=qs.filter(Q(assigned_to=emp)|Q(assigned_by_user=user))
   else: qs=qs.none()
  status_filter=self.request.query_params.get('status')
  if status_filter=='open': qs=qs.exclude(status__in=['COMPLETED','CANCELLED'])
  elif status_filter: qs=qs.filter(status=status_filter)
  if self.request.query_params.get('overdue')=='true': qs=qs.filter(due_date__lt=timezone.now()).exclude(status__in=['COMPLETED','CANCELLED'])
  return qs.select_related('assigned_to__user','related_customer','related_lead','related_application')
 @action(detail=False,methods=['get'])
 def my_tasks(self,request):
  emp=getattr(request.user,'employee',None); qs=self.get_queryset().filter(assigned_to=emp) if emp else self.get_queryset().none(); return Response(self.get_serializer(qs.order_by('due_date'),many=True).data)
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
 serializer_class=CustomerFollowUpSerializer; permission_classes=[IsAuthenticatedTenant]; filterset_fields=['customer','status','followup_type']
 def get_queryset(self):
  org=get_user_organization(self.request.user,self.request); qs=CostomerFollowUp.objects.filter(organization=org) if org else CostomerFollowUp.objects.none()
  return scope_followups(qs,CostomerFollowUp,self.request.user,self.request)
class LeadFollowUpViewSet(viewsets.ModelViewSet):
 serializer_class=LeadFollowUpSerializer; permission_classes=[IsAuthenticatedTenant]; filterset_fields=['lead','status','followup_type']
 def get_queryset(self):
  org=get_user_organization(self.request.user,self.request); qs=LeadFollowUp.objects.filter(organization=org) if org else LeadFollowUp.objects.none()
  return scope_followups(qs,LeadFollowUp,self.request.user,self.request)
class ApplicationFollowUpViewSet(viewsets.ModelViewSet):
 serializer_class=ApplicationFollowUpSerializer; permission_classes=[IsAuthenticatedTenant]; filterset_fields=['application','status','followup_type']
 def get_queryset(self):
  org=get_user_organization(self.request.user,self.request); qs=applicationFollowUp.objects.filter(organization=org) if org else applicationFollowUp.objects.none()
  return scope_followups(qs,applicationFollowUp,self.request.user,self.request)

@api_view(['GET'])
@permission_classes([IsAuthenticatedTenant])
def followups_today(request):
 org=get_user_organization(request.user,request); day=timezone.localdate(); result=[]
 ctx=get_user_role_context(request.user,request); level=ctx['hierarchy_level']; user=request.user; employee=getattr(user,'employee',None)
 manager=user.manager_set.first() if level>=70 and hasattr(user,'manager_set') else None; depts=manager.managed_departments.all() if manager else []
 teamlead=user.teamlead_profiles.first() if 50<=level<70 and hasattr(user,'teamlead_profiles') else None; teams=teamlead.teams.all() if teamlead else []
 for model,field,kind in [(CostomerFollowUp,'customer','customer'),(LeadFollowUp,'lead','lead'),(applicationFollowUp,'application','application')]:
  qs=model.objects.filter(organization=org,scheduled_at__date=day,status='PENDING')
  if ctx['role_code']=='sales_analyst' and employee:
   ref={CostomerFollowUp:'customer__converted_from_leads__assigned_sales_analyst',LeadFollowUp:'lead__assigned_sales_analyst',applicationFollowUp:'application__lead__assigned_sales_analyst'}[model]
   qs=qs.filter(Q(created_by=employee)|Q(**{ref:employee})).distinct()
  elif ctx['role_code'] in ('doc_officer','document_verification_officer') and employee:
   ref={CostomerFollowUp:'customer__converted_from_leads__assigned_doc_officer',LeadFollowUp:'lead__assigned_doc_officer',applicationFollowUp:'application__lead__assigned_doc_officer'}[model]
   qs=qs.filter(Q(created_by=employee)|Q(**{ref:employee})).distinct()
  elif level<50: qs=qs.filter(created_by=employee) if employee else qs.none()
  elif level<70:
   ref={CostomerFollowUp:'customer__created_by__team',LeadFollowUp:'lead__assigned_to__team',applicationFollowUp:'application__assigned_employee__team'}[model]
   qs=qs.filter(**{ref+'__in':teams})
  elif level<90:
   ref={CostomerFollowUp:'customer__created_by__department',LeadFollowUp:'lead__assigned_to__department',applicationFollowUp:'application__assigned_employee__department'}[model]
   qs=qs.filter(**{ref+'__in':depts})
  for obj in qs.order_by('scheduled_at'):
   result.append({'id':str(obj.pk),'kind':kind,'entity_id':str(getattr(obj,field+'_id')),'scheduled_at':obj.scheduled_at,'followup_type':obj.followup_type,'notes':obj.notes})
 return Response(sorted(result,key=lambda item:item['scheduled_at']))

@api_view(['GET'])
@permission_classes([IsAuthenticatedTenant])
def dashboard(request, role):
 org=get_user_organization(request.user,request); ctx=get_user_role_context(request.user,request); level=ctx['hierarchy_level']; emp=getattr(request.user,'employee',None)
 if not org:return Response({'detail':'Organization not found.'},status=400)
 required={'admin':90,'manager':70,'teamlead':50,'employee':30,'sales_analyst':30,'document_officer':30,'departments':70,'tasks':30}.get(role)
 if required is None:return Response({'detail':'Unknown dashboard.'},status=404)
 if level<required:return Response({'detail':'You do not have access to this dashboard.'},status=403)
 apps=FinancialApplication.objects.filter(organization=org); leads=Lead.objects.filter(organization=org); tasks=Task.objects.filter(organization=org); customers=Customer.objects.filter(organization=org)
 docs=Document.objects.filter(organization=org); payments=RepaymentPayment.objects.filter(organization=org)
 if ctx['role_code']=='sales_analyst':
  apps=apps.filter(lead__assigned_sales_analyst=emp); leads=leads.filter(assigned_sales_analyst=emp)
  customers=customers.filter(Q(created_by=emp)|Q(assigned_to=emp)|Q(converted_from_leads__assigned_sales_analyst=emp)).distinct()
  docs=docs.filter(application__lead__assigned_sales_analyst=emp)
  payments=payments.filter(Q(recorded_by=emp)|Q(repayment_schedule__application__lead__assigned_sales_analyst=emp))
  tasks=tasks.filter(assigned_to=emp)
 elif ctx['role_code'] in ('doc_officer','document_verification_officer'):
  apps=apps.filter(lead__assigned_doc_officer=emp); leads=leads.filter(assigned_doc_officer=emp)
  customers=customers.filter(Q(assigned_to=emp)|Q(converted_from_leads__assigned_doc_officer=emp)).distinct()
  docs=docs.filter(application__lead__assigned_doc_officer=emp); tasks=tasks.filter(assigned_to=emp)
  payments=payments.filter(repayment_schedule__application__lead__assigned_doc_officer=emp)
 elif ctx['role_code'] in ('finance_analyst','financial_analyst'):
  pass
 elif level>=70 and level<90:
  profile=request.user.manager_set.first() if hasattr(request.user,'manager_set') else None
  depts=profile.managed_departments.all() if profile else []
  apps=apps.filter(assigned_employee__department__in=depts); leads=leads.filter(Q(assigned_to__department__in=depts)|Q(created_by__department__in=depts)); tasks=tasks.filter(Q(department__in=depts)|Q(assigned_to__department__in=depts)); customers=customers.filter(Q(created_by__department__in=depts)|Q(assigned_to__department__in=depts)).distinct()
  docs=docs.filter(application__assigned_employee__department__in=depts); payments=payments.filter(repayment_schedule__application__assigned_employee__department__in=depts)
 elif level>=50 and level<70:
  profile=request.user.teamlead_profiles.first() if hasattr(request.user,'teamlead_profiles') else None
  teams=profile.teams.all() if profile else []
  apps=apps.filter(assigned_employee__team__in=teams); leads=leads.filter(Q(assigned_to__team__in=teams)|Q(created_by__team__in=teams)); tasks=tasks.filter(Q(team__in=teams)|Q(assigned_to__team__in=teams)); customers=customers.filter(Q(created_by__team__in=teams)|Q(assigned_to__team__in=teams)).distinct()
  docs=docs.filter(application__assigned_employee__team__in=teams); payments=payments.filter(repayment_schedule__application__assigned_employee__team__in=teams)
 elif emp:
  apps=apps.filter(assigned_employee=emp); leads=leads.filter(Q(assigned_to=emp)|Q(created_by=emp)); tasks=tasks.filter(assigned_to=emp); customers=customers.filter(Q(created_by=emp)|Q(assigned_to=emp)).distinct()
  docs=docs.filter(Q(application__assigned_employee=emp)|Q(customer__created_by=emp)); payments=payments.filter(Q(recorded_by=emp)|Q(repayment_schedule__application__assigned_employee=emp))
 status_rows=list(apps.values('status').annotate(count=Count('id')))
 lead_count=leads.count(); converted=leads.filter(converted_customer__isnull=False).count()
 completion_total=tasks.exclude(status='CANCELLED').count(); completion_rate=round(tasks.filter(status='COMPLETED').count()*100/completion_total,2) if completion_total else 0
 day=timezone.localdate(); schedules=RepaymentSchedule.objects.filter(organization=org,due_date__lt=day,status__in=['PENDING','PARTIAL'])
 if ctx['role_code']=='sales_analyst': schedules=schedules.filter(application__lead__assigned_sales_analyst=emp)
 if role=='document_officer' or ctx['role_code'] in ('doc_officer','document_verification_officer'): schedules=schedules.filter(application__lead__assigned_doc_officer=emp)
 team_performance=list(tasks.values('assigned_to__team__id','assigned_to__team__name').annotate(total_tasks=Count('id'),completed_tasks=Count('id',filter=Q(status='COMPLETED'))).order_by('assigned_to__team__name')) if role in ('manager','teamlead','admin') else []
 departments=Department.objects.filter(organization=org)
 if role=='departments' and level<90:
  manager=request.user.manager_set.first() if hasattr(request.user,'manager_set') else None
  departments=departments.filter(pk__in=manager.managed_departments.values('id')) if manager else departments.none()
 department_performance=[{'id':str(department.id),'name':department.name,'teams':department.team_set.count(),'employees':department.employee_set.count(),'applications':apps.filter(assigned_employee__department=department).count(),'tasks':tasks.filter(department=department).count()} for department in departments]
 data={'role':role,'customers':customers.count(),'leads':lead_count,'leads_converted':converted,'conversion_rate':round(converted*100/lead_count,2) if lead_count else 0,'applications':apps.count(),'applications_approved':apps.filter(status='approved').count(),'applications_rejected':apps.filter(status='rejected').count(),'applications_pending':apps.filter(status__in=['draft','submitted','under_review']).count(),'application_status':status_rows,'tasks_open':tasks.exclude(status__in=['COMPLETED','CANCELLED']).count(),'tasks_completed':tasks.filter(status='COMPLETED').count(),'tasks_overdue':tasks.filter(due_date__lt=timezone.now()).exclude(status__in=['COMPLETED','CANCELLED']).count(),'task_completion_rate':completion_rate,'team_performance':team_performance,'department_performance':department_performance if role in ('departments','admin') else [],'documents_received':docs.count(),'documents_pending':docs.filter(status='uploaded').count(),'documents_verified':docs.filter(status='accepted').count(),'documents_rejected':docs.filter(status='rejected').count(),'payments_recorded':payments.count(),'verified_revenue':payments.filter(verification_status='VERIFIED').aggregate(total=Sum('amount'))['total'] or 0,'pending_payments':payments.filter(verification_status='PENDING').count(),'overdue_installments':schedules.count(),'overdue_expected_amount':schedules.aggregate(total=Sum('expected_amount'))['total'] or 0,'disbursed_amount':apps.filter(status='disbursed').aggregate(total=Sum('disbursed_amount'))['total'] or 0}
 return Response(data)

# Create your views here.
