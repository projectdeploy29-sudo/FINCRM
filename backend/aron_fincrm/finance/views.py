from django.db import transaction
from django.db.models import Q
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from organizations.tenant import get_user_organization, get_user_role_context
from organizations.dates import organization_local_date
from permitions.permissions import IsAuthenticatedTenant
from finance.models import RepaymentSchedule, RepaymentPayment, RepaymentHistory
from finance.serializers import RepaymentScheduleSerializer, RepaymentPaymentSerializer

class RepaymentScheduleViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=RepaymentScheduleSerializer; permission_classes=[IsAuthenticatedTenant]
    filterset_fields=['lead','customer','status','payment_type']
    search_fields=['lead__lead_code','customer__full_name','notes']
    ordering_fields=['due_date','installment_number','expected_amount','status']
    def get_queryset(self):
        org=get_user_organization(self.request.user,self.request)
        if not org:return RepaymentSchedule.objects.none()
        qs=RepaymentSchedule.objects.filter(organization=org).select_related('customer','lead')
        if self.request.query_params.get('overdue')=='true': qs=qs.filter(due_date__lt=organization_local_date(self.request),status__in=['PENDING','PARTIAL'])
        role=get_user_role_context(self.request.user,self.request); level=role['hierarchy_level']; user=self.request.user
        if level>=90:return qs
        if level>=70:
            manager=user.manager_set.first() if hasattr(user,'manager_set') else None; depts=manager.managed_departments.all() if manager else []
            return qs.filter(lead__assigned_to__department__in=depts)
        if level>=50:
            profile=user.teamlead_profiles.first() if hasattr(user,'teamlead_profiles') else None; teams=profile.teams.all() if profile else []
            return qs.filter(lead__assigned_to__team__in=teams)
        employee=getattr(user,'employee',None)
        return qs.filter(lead__assigned_to=employee) if employee else qs.none()
    @action(detail=False,methods=['post'])
    def generate(self,request):
        ctx=get_user_role_context(request.user,request)
        if ctx['hierarchy_level']<30:
            return Response({'detail':'A staff account is required to generate a repayment schedule.'},status=403)
        lead_id=request.data.get('lead')
        start=request.data.get('first_due_date')
        amount=request.data.get('amount')
        raw_count=request.data.get('installments')
        from leads.models import Lead
        lead_qs=Lead.objects.filter(id=lead_id,organization=get_user_organization(request.user,request),status='disbursed')
        if ctx['hierarchy_level'] == 70:
            manager=request.user.manager_set.first() if hasattr(request.user,'manager_set') else None
            lead_qs=lead_qs.filter(assigned_to__department__in=manager.managed_departments.all()) if manager else lead_qs.none()
        elif 50 <= ctx['hierarchy_level'] < 70:
            profile=request.user.teamlead_profiles.first()
            lead_qs=lead_qs.filter(assigned_to__team__in=profile.teams.all()) if profile else lead_qs.none()
        elif 30 <= ctx['hierarchy_level'] < 50:
            employee=getattr(request.user,'employee',None)
            lead_qs=lead_qs.filter(assigned_to=employee) if employee else lead_qs.none()
        lead=lead_qs.first()
        if not lead: return Response({'detail':'Disbursed lead not found.'},status=400)
        try: count=int(raw_count or lead.loan_tenure_months or 0)
        except (TypeError,ValueError): return Response({'detail':'Installments must be a whole number.'},status=400)
        if lead.loan_tenure_months and count!=lead.loan_tenure_months:
            return Response({'detail':'Installment count must match the approved loan tenure.'},status=400)
        if not start or count<1 or count>600: return Response({'detail':'Provide a valid first_due_date and 1 to 600 installments.'},status=400)
        from datetime import date
        from decimal import Decimal, InvalidOperation
        try: due=date.fromisoformat(start)
        except Exception: return Response({'detail':'Invalid date or amount.'},status=400)
        from organizations.dates import organization_timezone
        from finance.amortization import build_emi_schedule
        payment_type=request.data.get('payment_type','EMI')
        if payment_type not in dict(RepaymentSchedule.PaymentType.choices):return Response({'detail':'Unknown payment type.'},status=400)
        with transaction.atomic():
            lead=Lead.objects.select_for_update().get(pk=lead.pk,organization=lead.organization)
            if lead.repayment_schedules.exists():return Response({'detail':'A repayment schedule already exists for this lead.'},status=409)
            principal=lead.disbursed_amount
            if principal is None or principal<=0:return Response({'detail':'The lead has no valid interest-bearing principal.'},status=400)
            if amount not in (None,''):
                try: requested_principal=Decimal(str(amount))
                except (InvalidOperation,TypeError):return Response({'detail':'Provide a valid principal amount.'},status=400)
                if requested_principal!=principal:
                    return Response({'detail':'The schedule principal must match the interest-bearing loan principal recorded at disbursement.'},status=400)
            if request.data.get('annual_interest_rate') not in (None,''):
                try: supplied_rate=Decimal(str(request.data['annual_interest_rate']))
                except (InvalidOperation,TypeError):return Response({'detail':'Provide a valid annual interest rate.'},status=400)
                if supplied_rate!=lead.annual_interest_rate:
                    return Response({'detail':'Interest terms are set on the lead and cannot be changed while generating the schedule.'},status=400)
            if request.data.get('interest_calculation_method') not in (None,'',lead.interest_calculation_method):
                return Response({'detail':'Interest terms are set on the lead and cannot be changed while generating the schedule.'},status=400)
            annual_rate=lead.annual_interest_rate
            if annual_rate is None or annual_rate<0 or annual_rate>100:
                return Response({'detail':'Set a valid annual interest rate on the lead before generating its schedule.'},status=400)
            if lead.disbursed_at:
                disbursement_date=lead.disbursed_at.astimezone(organization_timezone(request)).date()
                if due<=disbursement_date:
                    return Response({'detail':'The first due date must be after the loan disbursement date.'},status=400)
            else:
                disbursement_date=None
            if payment_type=='EMI':
                try:
                    rows,each,total_interest=build_emi_schedule(
                        principal=principal,
                        annual_rate_percent=annual_rate,
                        count=count,
                        first_due_date=due,
                        calculation_method=lead.interest_calculation_method,
                        disbursement_date=disbursement_date,
                    )
                except ValueError as error:
                    return Response({'detail':str(error)},status=400)
            else:
                rows,each,total_interest=build_emi_schedule(
                    principal=principal,
                    annual_rate_percent=0,
                    count=count,
                    first_due_date=due,
                    calculation_method='monthly_reducing',
                )
            lead.annual_interest_rate=annual_rate
            lead.loan_tenure_months=count
            lead.monthly_repayment_amount=each
            lead.next_payment_due_date=due
            lead.save(update_fields=['annual_interest_rate','loan_tenure_months','monthly_repayment_amount','next_payment_due_date','updated_at'])
            schedules=[]
            for item in rows:
                schedules.append(RepaymentSchedule.objects.create(
                    organization=lead.organization,
                    customer=lead.customer,
                    lead=lead,
                    payment_type=payment_type,
                    installment_number=item['installment_number'],
                    expected_amount=item['expected_amount'],
                    due_date=item['due_date'],
                    opening_balance=item['opening_balance'],
                    principal_due=item['principal_due'],
                    interest_due=item['interest_due'],
                    interest_days=item['interest_days'],
                    closing_balance=item['closing_balance'],
                ))
        return Response(RepaymentScheduleSerializer(schedules,many=True,context={'request':request}).data,status=201)

class RepaymentPaymentViewSet(viewsets.ModelViewSet):
    serializer_class=RepaymentPaymentSerializer; permission_classes=[IsAuthenticatedTenant]
    # Receipts are immutable after submission. Corrections must be rejected and
    # re-entered so the verification history remains auditable.
    http_method_names=['get','post','head','options']
    filterset_fields=['verification_status','repayment_schedule','payment_method']
    search_fields=['transaction_reference','notes','repayment_schedule__lead__lead_code','repayment_schedule__customer__full_name']
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
            return qs.filter(repayment_schedule__lead__assigned_to__department__in=depts)
        if level>=50:
            profile=user.teamlead_profiles.first() if hasattr(user,'teamlead_profiles') else None; teams=profile.teams.all() if profile else []
            return qs.filter(repayment_schedule__lead__assigned_to__team__in=teams)
        employee=getattr(user,'employee',None)
        return qs.filter(Q(recorded_by=employee)|Q(repayment_schedule__lead__assigned_to=employee)) if employee else qs.none()
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
