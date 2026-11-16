from django.db import transaction
from django.db.models import Sum, Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.http import FileResponse
from django.utils import timezone
from organizations.tenant import get_user_organization, get_user_role_context
from permitions.permissions import IsAuthenticatedTenant
from finance.models import RepaymentSchedule, RepaymentPayment, RepaymentHistory
from finance.serializers import RepaymentScheduleSerializer, RepaymentPaymentSerializer

class RepaymentScheduleViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=RepaymentScheduleSerializer; permission_classes=[IsAuthenticatedTenant]
    filterset_fields=['application','customer','status','payment_type']
    def get_queryset(self):
        org=get_user_organization(self.request.user,self.request)
        if not org:return RepaymentSchedule.objects.none()
        qs=RepaymentSchedule.objects.filter(organization=org).select_related('customer','application')
        if self.request.query_params.get('overdue')=='true': qs=qs.filter(due_date__lt=timezone.localdate(),status__in=['PENDING','PARTIAL'])
        role=get_user_role_context(self.request.user,self.request); level=role['hierarchy_level']; user=self.request.user
        if level>=90:return qs
        if role['role_code'] in ('finance_analyst','financial_analyst'):return qs
        if role['role_code']=='sales_analyst':
            employee=getattr(user,'employee',None)
            return qs.filter(application__lead__assigned_sales_analyst=employee) if employee else qs.none()
        if level>=70:
            manager=user.manager_set.first() if hasattr(user,'manager_set') else None; depts=manager.managed_departments.all() if manager else []
            return qs.filter(application__assigned_employee__department__in=depts)
        if level>=50:
            profile=user.teamlead_profiles.first() if hasattr(user,'teamlead_profiles') else None; teams=profile.teams.all() if profile else []
            return qs.filter(application__assigned_employee__team__in=teams)
        employee=getattr(user,'employee',None)
        return qs.filter(application__assigned_employee=employee) if employee else qs.none()
    @action(detail=False,methods=['post'])
    def generate(self,request):
        ctx=get_user_role_context(request.user,request)
        if ctx['role_code'] not in ('org_admin','manager','super_admin','finance_analyst','financial_analyst','sales_analyst'):
            return Response({'detail':'Finance analyst, manager, or organization admin role required.'},status=403)
        app_id=request.data.get('application'); start=request.data.get('first_due_date'); amount=request.data.get('amount')
        try: count=int(request.data.get('installments',1))
        except (TypeError,ValueError): return Response({'detail':'Installments must be a whole number.'},status=400)
        from applications.models import FinancialApplication
        application_qs=FinancialApplication.objects.filter(id=app_id,organization=get_user_organization(request.user,request),status='approved')
        if ctx['hierarchy_level'] == 70:
            manager=request.user.manager_set.first() if hasattr(request.user,'manager_set') else None
            application_qs=application_qs.filter(assigned_employee__department__in=manager.managed_departments.all()) if manager else application_qs.none()
        application=application_qs.first()
        if not application: return Response({'detail':'Approved application not found.'},status=400)
        if not start or count<1 or count>600: return Response({'detail':'Provide a valid first_due_date and 1 to 600 installments.'},status=400)
        from datetime import date
        from decimal import Decimal
        try: due=date.fromisoformat(start); total=Decimal(str(amount or application.approved_amount or application.requested_amount))
        except Exception: return Response({'detail':'Invalid date or amount.'},status=400)
        if total<=0:return Response({'detail':'Amount must be greater than zero.'},status=400)
        rate=request.data.get('annual_interest_rate',0)
        try: annual_rate=Decimal(str(rate))
        except Exception:return Response({'detail':'annual_interest_rate must be a non-negative number.'},status=400)
        if annual_rate<0 or annual_rate>100:return Response({'detail':'annual_interest_rate must be between 0 and 100.'},status=400)
        payment_type=request.data.get('payment_type','EMI')
        if payment_type not in dict(RepaymentSchedule.PaymentType.choices):return Response({'detail':'Unknown payment type.'},status=400)
        if payment_type=='EMI' and annual_rate:
            from decimal import localcontext
            monthly_rate=annual_rate/Decimal('1200')
            with localcontext() as ctx:
                ctx.prec=28; factor=(Decimal('1')+monthly_rate)**count
                each=(total*monthly_rate*factor/(factor-1)).quantize(Decimal('0.01'))
        else: each=(total/count).quantize(Decimal('0.01'))
        rows=[]
        with transaction.atomic():
            application=FinancialApplication.objects.select_for_update().get(pk=application.pk,organization=application.organization)
            if application.repayment_schedules.exists():return Response({'detail':'A repayment schedule already exists for this application.'},status=409)
            for n in range(count):
                month_index=due.month-1+n; year=due.year+month_index//12; month=month_index%12+1
                import calendar
                due_date=due.replace(year=year,month=month,day=min(due.day,calendar.monthrange(year,month)[1]))
                installment_amount=each if payment_type=='EMI' and annual_rate else (each if n<count-1 else total-each*(count-1))
                rows.append(RepaymentSchedule.objects.create(organization=application.organization,customer=application.customer,application=application,lead=application.lead,payment_type=payment_type,installment_number=n+1,expected_amount=installment_amount,due_date=due_date))
        return Response(RepaymentScheduleSerializer(rows,many=True).data,status=201)

class RepaymentPaymentViewSet(viewsets.ModelViewSet):
    serializer_class=RepaymentPaymentSerializer; permission_classes=[IsAuthenticatedTenant]
    filterset_fields=['verification_status','repayment_schedule','payment_method']
    def get_permissions(self):
        from permitions.permissions import IsOrgAdmin
        if self.action=='destroy':return [IsAuthenticatedTenant(),IsOrgAdmin()]
        return [IsAuthenticatedTenant()]
    def get_queryset(self):
        org=get_user_organization(self.request.user,self.request)
        if not org:return RepaymentPayment.objects.none()
        qs=RepaymentPayment.objects.filter(organization=org).select_related('repayment_schedule','recorded_by__user')
        ctx=get_user_role_context(self.request.user,self.request); level=ctx['hierarchy_level']; user=self.request.user
        if level>=90:return qs
        if ctx['role_code'] in ('finance_analyst','financial_analyst'):return qs
        if ctx['role_code']=='sales_analyst':
            employee=getattr(user,'employee',None)
            return qs.filter(Q(recorded_by=employee)|Q(repayment_schedule__application__lead__assigned_sales_analyst=employee)) if employee else qs.none()
        if level>=70:
            manager=user.manager_set.first() if hasattr(user,'manager_set') else None; depts=manager.managed_departments.all() if manager else []
            return qs.filter(repayment_schedule__application__assigned_employee__department__in=depts)
        if level>=50:
            profile=user.teamlead_profiles.first() if hasattr(user,'teamlead_profiles') else None; teams=profile.teams.all() if profile else []
            return qs.filter(repayment_schedule__application__assigned_employee__team__in=teams)
        employee=getattr(user,'employee',None)
        return qs.filter(Q(recorded_by=employee)|Q(repayment_schedule__application__assigned_employee=employee)) if employee else qs.none()
    @action(detail=True,methods=['get'])
    def proof(self,request,pk=None):
        payment=self.get_object()
        if not payment.payment_proof:return Response({'detail':'No payment proof has been uploaded.'},status=404)
        return FileResponse(payment.payment_proof.open('rb'),as_attachment=True,filename=payment.payment_proof.name.rsplit('/',1)[-1])
    @action(detail=True,methods=['post'])
    def verify(self,request,pk=None):
        role=get_user_role_context(request.user,request)
        if role['hierarchy_level']<70 and role['role_code'] not in ('finance_analyst','financial_analyst','sales_analyst'): return Response({'detail':'Finance or sales analyst, manager, or organization admin role required.'},status=403)
        payment=self.get_object(); decision=request.data.get('verification_status')
        if decision not in ('VERIFIED','REJECTED'): return Response({'detail':'verification_status must be VERIFIED or REJECTED.'},status=400)
        if payment.verification_status!='PENDING':return Response({'detail':'Only pending payments can be reviewed.'},status=400)
        with transaction.atomic():
            payment=RepaymentPayment.objects.select_for_update().get(pk=payment.pk)
            old=payment.verification_status; payment.verification_status=decision; payment.verified_by=getattr(request.user,'employee',None); payment.save(update_fields=['verification_status','verified_by'])
            RepaymentHistory.objects.create(organization=payment.organization,repayment=payment,action='verification',previous_value={'status':old},new_value={'status':decision},description=request.data.get('notes',''),performed_by=request.user)
            if decision=='VERIFIED':
                schedule=RepaymentSchedule.objects.select_for_update().get(pk=payment.repayment_schedule_id)
                schedule.status='PAID' if schedule.outstanding_amount <= 0 else 'PARTIAL'; schedule.save(update_fields=['status','updated_at'])
        return Response(self.get_serializer(payment).data)

# Create your views here.
