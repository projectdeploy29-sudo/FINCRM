from django.db import transaction
from django.db.models import Sum, Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from organizations.tenant import get_user_organization, get_user_role_context
from organizations.dates import organization_local_date
from permitions.permissions import IsAuthenticatedTenant
from finance.models import RepaymentSchedule, RepaymentPayment, RepaymentHistory
from finance.serializers import RepaymentScheduleSerializer, RepaymentPaymentSerializer

class RepaymentScheduleViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=RepaymentScheduleSerializer; permission_classes=[IsAuthenticatedTenant]
    filterset_fields=['application','customer','status','payment_type']
    search_fields=['application__application_code','customer__full_name','notes']
    ordering_fields=['due_date','installment_number','expected_amount','status']
    def get_queryset(self):
        org=get_user_organization(self.request.user,self.request)
        if not org:return RepaymentSchedule.objects.none()
        qs=RepaymentSchedule.objects.filter(organization=org).select_related('customer','application','lead')
        if self.request.query_params.get('overdue')=='true': qs=qs.filter(due_date__lt=organization_local_date(self.request),status__in=['PENDING','PARTIAL'])
        role=get_user_role_context(self.request.user,self.request); level=role['hierarchy_level']; user=self.request.user
        if level>=90:return qs
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
        if ctx['hierarchy_level']<30:
            return Response({'detail':'A staff account is required to generate a repayment schedule.'},status=403)
        app_id=request.data.get('application'); start=request.data.get('first_due_date'); amount=request.data.get('amount')
        raw_count=request.data.get('installments')
        from applications.models import FinancialApplication
        application_qs=FinancialApplication.objects.filter(id=app_id,organization=get_user_organization(request.user,request),status='disbursed')
        if ctx['hierarchy_level'] == 70:
            manager=request.user.manager_set.first() if hasattr(request.user,'manager_set') else None
            application_qs=application_qs.filter(assigned_employee__department__in=manager.managed_departments.all()) if manager else application_qs.none()
        elif 50 <= ctx['hierarchy_level'] < 70:
            profile=request.user.teamlead_profiles.first()
            application_qs=application_qs.filter(assigned_employee__team__in=profile.teams.all()) if profile else application_qs.none()
        elif 30 <= ctx['hierarchy_level'] < 50:
            employee=getattr(request.user,'employee',None)
            application_qs=application_qs.filter(assigned_employee=employee) if employee else application_qs.none()
        application=application_qs.first()
        if not application: return Response({'detail':'Disbursed application not found.'},status=400)
        try: count=int(raw_count or application.loan_tenure_months or 0)
        except (TypeError,ValueError): return Response({'detail':'Installments must be a whole number.'},status=400)
        if application.loan_tenure_months and count!=application.loan_tenure_months:
            return Response({'detail':'Installment count must match the approved loan tenure.'},status=400)
        if not start or count<1 or count>600: return Response({'detail':'Provide a valid first_due_date and 1 to 600 installments.'},status=400)
        from datetime import date
        from decimal import Decimal
        try: due=date.fromisoformat(start); total=Decimal(str(application.disbursed_amount if amount in (None,'') else amount))
        except Exception: return Response({'detail':'Invalid date or amount.'},status=400)
        if total<=0:return Response({'detail':'Amount must be greater than zero.'},status=400)
        if application.disbursed_amount is not None and total!=application.disbursed_amount:
            return Response({'detail':'Repayment schedule principal must match the actual disbursed loan amount.'},status=400)
        rate=request.data.get('annual_interest_rate',application.annual_interest_rate or 0)
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
            application.annual_interest_rate=annual_rate
            application.loan_tenure_months=count
            application.monthly_repayment_amount=each
            application.next_payment_due_date=due
            application.save(update_fields=['annual_interest_rate','loan_tenure_months','monthly_repayment_amount','next_payment_due_date','updated_at'])
            for n in range(count):
                month_index=due.month-1+n; year=due.year+month_index//12; month=month_index%12+1
                import calendar
                due_date=due.replace(year=year,month=month,day=min(due.day,calendar.monthrange(year,month)[1]))
                installment_amount=each if payment_type=='EMI' and annual_rate else (each if n<count-1 else total-each*(count-1))
                rows.append(RepaymentSchedule.objects.create(organization=application.organization,customer=application.customer,application=application,lead=application.lead,payment_type=payment_type,installment_number=n+1,expected_amount=installment_amount,due_date=due_date))
        return Response(RepaymentScheduleSerializer(rows,many=True,context={'request':request}).data,status=201)

class RepaymentPaymentViewSet(viewsets.ModelViewSet):
    serializer_class=RepaymentPaymentSerializer; permission_classes=[IsAuthenticatedTenant]
    # Receipts are immutable after submission. Corrections must be rejected and
    # re-entered so the verification history remains auditable.
    http_method_names=['get','post','head','options']
    filterset_fields=['verification_status','repayment_schedule','payment_method']
    search_fields=['transaction_reference','notes','repayment_schedule__application__application_code','repayment_schedule__customer__full_name']
    ordering_fields=['payment_date','created_at','amount','verification_status']
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
        if level>=70:
            manager=user.manager_set.first() if hasattr(user,'manager_set') else None; depts=manager.managed_departments.all() if manager else []
            return qs.filter(repayment_schedule__application__assigned_employee__department__in=depts)
        if level>=50:
            profile=user.teamlead_profiles.first() if hasattr(user,'teamlead_profiles') else None; teams=profile.teams.all() if profile else []
            return qs.filter(repayment_schedule__application__assigned_employee__team__in=teams)
        employee=getattr(user,'employee',None)
        return qs.filter(Q(recorded_by=employee)|Q(repayment_schedule__application__assigned_employee=employee)) if employee else qs.none()
    @action(detail=True,methods=['post'])
    def verify(self,request,pk=None):
        role=get_user_role_context(request.user,request)
        if role['hierarchy_level']<30: return Response({'detail':'A staff account is required to verify a payment.'},status=403)
        payment=self.get_object(); decision=request.data.get('verification_status')
        if decision not in ('VERIFIED','REJECTED'): return Response({'detail':'verification_status must be VERIFIED or REJECTED.'},status=400)
        reviewer=getattr(request.user,'employee',None)
        if reviewer and payment.recorded_by_id==reviewer.id:
            return Response({'detail':'The employee who recorded a payment cannot review it.'},status=403)
        with transaction.atomic():
            payment=RepaymentPayment.objects.select_for_update().get(pk=payment.pk,organization=get_user_organization(request.user,request))
            if payment.verification_status!='PENDING':
                return Response({'detail':'Only pending payments can be reviewed.'},status=400)
            old=payment.verification_status; payment.verification_status=decision; payment.verified_by=getattr(request.user,'employee',None); payment.save(update_fields=['verification_status','verified_by'])
            RepaymentHistory.objects.create(organization=payment.organization,repayment=payment,action='verification',previous_value={'status':old},new_value={'status':decision},description=request.data.get('notes',''),performed_by=request.user)
            if decision=='VERIFIED':
                schedule=RepaymentSchedule.objects.select_for_update().get(pk=payment.repayment_schedule_id)
                schedule.status='PAID' if schedule.outstanding_amount <= 0 else 'PARTIAL'; schedule.save(update_fields=['status','updated_at'])
        return Response(self.get_serializer(payment).data)

# Create your views here.
