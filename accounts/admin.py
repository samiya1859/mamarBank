from django.contrib import admin
from .models import UserBankAccount,UserAddress,Bank
# Register your models here.
admin.site.register(UserBankAccount)
admin.site.register(UserAddress)
admin.site.register(Bank)

