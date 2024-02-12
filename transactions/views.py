from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.forms import BaseModelForm
from .forms import TransferBalanceForm
from django.urls import reverse_lazy
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect,render
from django.views import View
from django.http import HttpResponse
from django.views.generic import CreateView, ListView
from transactions.constants import DEPOSIT, WITHDRAWAL,LOAN, LOAN_PAID,TRANSFER,SEND_MONEY,RECEIVE_MONEY
from datetime import datetime
from django.core.mail import EmailMessage,EmailMultiAlternatives
from django.template.loader import render_to_string
from django.db.models import Sum
from accounts.models import Bank,UserBankAccount

from transactions.forms import (
    DepositForm,
    WithdrawForm,
    LoanRequestForm,
)
from transactions.models import Transaction

def send_transaction_email(user, amount, subject, template):
        message = render_to_string(template, {
            'user' : user,
            'amount' : amount,
        })
        send_email = EmailMultiAlternatives(subject, '', to=[user.email])
        send_email.attach_alternative(message, "text/html")
        send_email.send()

class TransactionCreateMixin(LoginRequiredMixin, CreateView):
    template_name = 'transactions/transaction_form.html'
    model = Transaction
    title = ''
    success_url = reverse_lazy('transaction_report')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({
            'account': self.request.user.account
        })
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs) # template e context data pass kora
        context.update({
            'title': self.title
        })

        return context


class DepositMoneyView(TransactionCreateMixin):
    form_class = DepositForm
    title = 'Deposit'

    def get_initial(self):
        initial = {'transaction_type': DEPOSIT}
        return initial

    def form_valid(self, form):
        amount = form.cleaned_data.get('amount')
        account = self.request.user.account
        # if not account.initial_deposit_date:
        #     now = timezone.now()
        #     account.initial_deposit_date = now
        account.balance += amount # amount = 200, tar ager balance = 0 taka new balance = 0+200 = 200
        account.save(
            update_fields=[
                'balance'
            ]
        )

        messages.success(
            self.request,
            f'{"{:,.2f}".format(float(amount))}$ was deposited to your account successfully'
        )
        mail_subject = "Deposit message"
        message = render_to_string('transactions/deposit_email.html',{
            'user': self.request.user,
            'amount':amount,
        })
        to_email = self.request.user.email
        send_email = EmailMultiAlternatives(mail_subject,message,to=[to_email])
        print("aa")
        send_email.attach_alternative(message,"text/html")
        send_email.send()

        return super().form_valid(form)


class WithdrawMoneyView(TransactionCreateMixin):
    form_class = WithdrawForm
    title = 'Withdraw Money'

    def get_initial(self):
        initial = {'transaction_type': WITHDRAWAL}
        return initial

    def form_valid(self, form):
        amount = form.cleaned_data.get('amount')

        self.request.user.account.balance -= form.cleaned_data.get('amount')
        # balance = 300
        # amount = 5000
        self.request.user.account.save(update_fields=['balance'])

        messages.success(
            self.request,
            f'Successfully withdrawn {"{:,.2f}".format(float(amount))}$ from your account'
        )
        send_transaction_email(self.request.user, amount, "Withdrawal Message", "transactions/withdrawal_email.html")
        return super().form_valid(form)
    
class LoanRequestView(TransactionCreateMixin):
    form_class = LoanRequestForm
    title = 'Request For Loan'

    def get_initial(self):
        initial = {'transaction_type': LOAN}
        return initial

    def form_valid(self, form):
        amount = form.cleaned_data.get('amount')
        current_loan_count = Transaction.objects.filter(
            account=self.request.user.account,transaction_type=3,loan_approve=True).count()
        if current_loan_count >= 3:
            return HttpResponse("You have cross the loan limits")
        messages.success(
            self.request,
            f'Loan request for {"{:,.2f}".format(float(amount))}$ submitted successfully'
        )
        send_transaction_email(self.request.user, amount, "Loan Request Message", "transactions/loan_email.html")
        return super().form_valid(form)
    
class TransactionReportView(LoginRequiredMixin, ListView):
    template_name = 'transactions/transaction_report.html'
    model = Transaction
    balance = 0 # filter korar pore ba age amar total balance ke show korbe
    
    def get_queryset(self):
        queryset = super().get_queryset().filter(
            account=self.request.user.account
        )
        start_date_str = self.request.GET.get('start_date')
        end_date_str = self.request.GET.get('end_date')
        
        if start_date_str and end_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            
            queryset = queryset.filter(timestamp__date__gte=start_date, timestamp__date__lte=end_date)
            self.balance = Transaction.objects.filter(
                timestamp__date__gte=start_date, timestamp__date__lte=end_date
            ).aggregate(Sum('amount'))['amount__sum']
        else:
            self.balance = self.request.user.account.balance
       
        return queryset.distinct() # unique queryset hote hobe
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'account': self.request.user.account
        })

        return context
    
        
class PayLoanView(LoginRequiredMixin, View):
    def get(self, request, loan_id):
        loan = get_object_or_404(Transaction, id=loan_id)
        print(loan)
        if loan.loan_approve:
            user_account = loan.account
                # Reduce the loan amount from the user's balance
                # 5000, 500 + 5000 = 5500
                # balance = 3000, loan = 5000
            if loan.amount < user_account.balance:
                user_account.balance -= loan.amount
                loan.balance_after_transaction = user_account.balance
                user_account.save()
                loan.loan_approved = True
                loan.transaction_type = LOAN_PAID
                loan.save()
                return redirect('transactions:loan_list')
            else:
                messages.error(
            self.request,
            f'Loan amount is greater than available balance'
        )

        return redirect('loan_list')


class LoanListView(LoginRequiredMixin,ListView):
    model = Transaction
    template_name = 'transactions/loan_request.html'
    context_object_name = 'loans' # loan list ta ei loans context er moddhe thakbe
    
    def get_queryset(self):
        user_account = self.request.user.account
        queryset = Transaction.objects.filter(account=user_account,transaction_type=3)
        print(queryset)
        return queryset
    

class TransferBalance(TransactionCreateMixin):
    form_class = TransferBalanceForm
    title = 'Transfer balance'
    def get_initial(self):
        initial = {'transaction_type' : TRANSFER}
        return initial
    
    def form_valid(self, form):
        amount = form.cleaned_data.get('amount')
        account_no = form.cleaned_data.get('account_no')
        print(account_no)

        self.request.user.account.balance -= form.cleaned_data.get('amount')
        self.request.user.account.save(update_fields=['balance'])

        messages.success(
            self.request,
            f'Successfully transferred {amount}$ from your account'
        )
        return super().form_valid(form)

    def post(self, request):
        form = TransferBalanceForm(data=request.POST)
        if form.is_valid():
            recipient_username = form.cleaned_data['recipient_username']
            amount = form.cleaned_data['amount']

            try:
                recipient_user = User.objects.get(username=recipient_username)
                recipient_account = recipient_user.account
            except User.DoesNotExist:
                messages.error(request, f"Recipient '{recipient_username}' does not exist.")
                return redirect('transfer')

            if amount <= 0:
                messages.error(request, "Amount must be greater than zero.")
                return redirect('transfer')

            sender_account = request.user.account
            if sender_account.balance < amount:
                messages.error(request, 'Insufficient balance.')
                return redirect('transfer')

            sender_account.balance -= amount
            sender_account.save()

            recipient_account.balance += amount
            recipient_account.save()

            # Create transaction records for sender and recipient
            Transaction.objects.create(
                account=sender_account,
                transaction_type=WITHDRAWAL,
                amount=amount,
                timestamp=timezone.now(),
                balance_after_transaction=sender_account.balance
            )

            Transaction.objects.create(
                account=recipient_account,
                transaction_type=DEPOSIT,
                amount=amount,
                timestamp=timezone.now(),
                balance_after_transaction=recipient_account.balance
            )

            # Send email notifications to sender and receiver
            

            messages.success(request, f"Successfully transferred {amount}$.")
            return redirect('transfer')
        else:
            return render(request, 'transactions/transfer_balance.html', {'form': form})

    


# def Transfer_Balance(request):
#     title = 'Transfer Balance'
#     if request.method == 'POST':
#         form = TransferBalanceForm(request.POST,account=request.user.account)
#         if form.is_valid():
#             sender_account = request.user.account
#             receiver_account_no = form.cleaned_data['receiver_account']
#             try:
#                 receiver_account = UserBankAccount.objects.get(account_no=receiver_account_no)
#             except UserBankAccount.DoesNotExist:
#                 print('Receiver account not found')
                
#                 return redirect('home')  # Redirect to an appropriate page

#             amount = form.cleaned_data['amount']

#             if sender_account.balance >= amount:
#                 sender_account.balance -= amount
#                 sender_account.save()
#                 send_transaction_email(sender_account.user, amount, 'Sent Money', 'transactions/transfer_email_sender.html')

#                 receiver_account.balance += amount
#                 receiver_account.save()
#                 send_transaction_email(receiver_account.user, amount, 'Received money', 'transactions/transfer_email_receiver.html')

#                 # Create transactions
#                 Transaction.objects.create(
#                     account=sender_account,
#                     amount=amount,
#                     balance_after_transaction=sender_account.balance,
#                     transaction_type=SEND_MONEY,
#                     loan_approve=False,
#                 )
#                 Transaction.objects.create(
#                     account=receiver_account,
#                     amount=amount,
#                     balance_after_transaction=receiver_account.balance,
#                     transaction_type=RECEIVE_MONEY,
#                     loan_approve=False,
#                 )

#                 return redirect('home')
#             else:
#                 print('Insufficient balance')
#                 # You may want to provide a user-friendly message here
#     else:
#         form = TransferBalanceForm(account=request.user.account)

#     return render(request, 'transactions/transfer_balance.html', {'form': form})


class TransferBalance(View):
    template_name = 'transactions/transfer_balance.html'
    form_class = TransferBalanceForm
    title = 'Transfer balance'

    def get_initial(self):
        return {'transaction_type': TRANSFER}

    def get(self, request):
        form = self.form_class()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = self.form_class(data=request.POST)
        if form.is_valid():
            recipient_username = form.cleaned_data['recipient_username']
            amount = form.cleaned_data['amount']

            try:
                recipient_user = User.objects.get(username=recipient_username)
                recipient_account = recipient_user.account
            except User.DoesNotExist:
                messages.error(request, f"Recipient '{recipient_username}' does not exist.")
                return redirect('transfer')

            sender_account = request.user.account
            if sender_account.balance < amount:
                messages.error(request, 'Insufficient balance.')
                return redirect('transfer')

            sender_account.balance -= amount
            sender_account.save()

            recipient_account.balance += amount
            recipient_account.save()

            # Create transaction records for sender and recipient
            sender_transaction = Transaction.objects.create(
                account=sender_account,
                transaction_type=TRANSFER,
                amount=amount,
                timestamp=timezone.now(),
                balance_after_transaction=sender_account.balance
            )

            recipient_transaction = Transaction.objects.create(
                account=recipient_account,
                transaction_type=RECEIVE_MONEY,
                amount=amount,
                timestamp=timezone.now(),
                balance_after_transaction=recipient_account.balance
            )

            # Send email notifications to sender and receiver
            self.send_transaction_email(request.user, recipient_user, amount)

            messages.success(request, f"Successfully transferred {amount}$.")
            return redirect('transfer')
        else:
            return render(request, self.template_name, {'form': form})
        
    def send_transaction_email(self, sender, recipient, amount):
        # Render the email content from HTML templates
        print("sender :",sender)
        print("recipient :",recipient)
        sender_message = render_to_string('transactions/transfer_email_sender.html', {
            'sender': sender,
            'recipient': recipient,
            'amount': amount,
        })
        sender_subject = f"You've transferred {amount}$"
        sender_email = EmailMultiAlternatives(sender_subject, sender_message, to=[sender.email])
        sender_email.attach_alternative(sender_message,"text/html")
        sender_email.send()
    
        recipient_message = render_to_string('transactions/transfer_email_recipient.html', {
            'sender': sender,
            'recipient': recipient,
            'amount': amount,
        })
        recipient_subject = f"You've received {amount}$"
        recipient_email = EmailMultiAlternatives(recipient_subject, recipient_message, to=[recipient.email])
        recipient_email.attach_alternative(recipient_message,"text/html")
        recipient_email.send()