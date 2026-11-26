from django.db import models
from django.conf import settings
from django.db.models import Sum
from django.utils import timezone


class RepaymentSchedule(models.Model):

    class PaymentType(models.TextChoices):
        EMI = "EMI", "Loan EMI"
        PREMIUM = "PREMIUM", "Insurance Premium"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PARTIAL = "PARTIAL", "Partially Paid"
        PAID = "PAID", "Paid"
        WAIVED = "WAIVED", "Waived"
        CANCELLED = "CANCELLED", "Cancelled"

    organization = models.ForeignKey(
        "organizations.organizations_organization",
        on_delete=models.CASCADE,
        related_name="repayment_schedules"
    )

    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        related_name="repayment_schedules"
    )

    lead = models.ForeignKey(
        "leads.Lead",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="repayment_schedules"
    )

    payment_type = models.CharField(
        max_length=20,
        choices=PaymentType.choices
    )

    installment_number = models.PositiveIntegerField()

    expected_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2
    )

    opening_balance = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    principal_due = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    interest_due = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    interest_days = models.PositiveIntegerField(null=True, blank=True)
    closing_balance = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    due_date = models.DateField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )

    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints=[models.UniqueConstraint(fields=['lead','installment_number'],name='uniq_lead_installment')]

    @property
    def received_amount(self):
        return self.payments.filter(
            verification_status="VERIFIED"
        ).aggregate(
            total=Sum("amount")
        )["total"] or 0

    @property
    def outstanding_amount(self):
        return max(self.expected_amount - self.received_amount, 0)

    @property
    def is_overdue(self):
        return (
            self.due_date < timezone.localdate()
            and self.outstanding_amount > 0
            and self.status not in [
                self.Status.WAIVED,
                self.Status.CANCELLED
            ]
        )

    def __str__(self):
        return f"{self.customer} - Installment {self.installment_number}"


class RepaymentPayment(models.Model):

    class PaymentMethod(models.TextChoices):
        CASH = "CASH", "Cash"
        UPI = "UPI", "UPI"
        BANK = "BANK", "Bank Transfer"
        CHEQUE = "CHEQUE", "Cheque"
        OTHER = "OTHER", "Other"

    class VerificationStatus(models.TextChoices):
        PENDING = "PENDING", "Pending Verification"
        VERIFIED = "VERIFIED", "Verified"
        REJECTED = "REJECTED", "Rejected"

    class PaymentRecipient(models.TextChoices):
        ORGANIZATION = "ORGANIZATION", "Organization"
        LENDER = "LENDER", "Bank / Lender"
        INSURER = "INSURER", "Insurance Company"
        OTHER = "OTHER", "Other"

    organization = models.ForeignKey(
        "organizations.organizations_organization",
        on_delete=models.CASCADE,
        related_name="repayment_payments"
    )

    repayment_schedule = models.ForeignKey(
        RepaymentSchedule,
        on_delete=models.PROTECT,
        related_name="payments"
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    payment_date = models.DateField()

    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices
    )

    payment_recipient = models.CharField(
        max_length=20,
        choices=PaymentRecipient.choices
    )

    transaction_reference = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    payment_proof = models.FileField(
        upload_to="repayment_proofs/",
        blank=True,
        null=True
    )

    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING
    )

    recorded_by = models.ForeignKey(
        "employes.Employee",
        on_delete=models.PROTECT,
        related_name="recorded_payments"
    )

    verified_by = models.ForeignKey(
        "employes.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_payments"
    )

    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.amount} - {self.repayment_schedule}"


class RepaymentHistory(models.Model):

    organization = models.ForeignKey(
        "organizations.organizations_organization",
        on_delete=models.CASCADE,
        related_name="repayment_histories"
    )

    repayment = models.ForeignKey(
        RepaymentPayment,
        on_delete=models.PROTECT,
        related_name="history"
    )

    action = models.CharField(max_length=100)

    previous_value = models.JSONField(
        null=True,
        blank=True
    )

    new_value = models.JSONField(
        null=True,
        blank=True
    )

    description = models.TextField(blank=True, null=True)

    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="repayment_actions"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action} - {self.repayment}"

