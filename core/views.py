from django.shortcuts import render
from django.views.generic import TemplateView
# from transactions.utils import is_bankrupt

class HomeView(TemplateView):
    template_name = 'index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # context['is_bankrupt'] = is_bankrupt()
        return context
