from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path('robots.txt', views.robots_txt, name='robots'),
    path('login/', auth_views.LoginView.as_view(template_name='twodapp/login.html'), name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('', views.index, name='index'),
    path('records/', views.records_page, name='records'),
    path('limit/', views.limit_page, name='limit'),
    path('ledger/', views.ledger_page, name='ledger'),
    path('api/parse', views.api_parse, name='api_parse'),
    path('api/live', views.api_live, name='api_live'),
    path('api/set_global_limit', views.api_set_global_limit, name='api_set_global_limit'),
    path('api/set_specific_limit', views.api_set_specific_limit, name='api_set_specific_limit'),
    path('api/delete_specific_limit', views.api_delete_specific_limit, name='api_delete_specific_limit'),
    path('api/save_meta', views.api_save_meta, name='api_save_meta'),
    path('api/clear_all', views.api_clear_all, name='api_clear_all'),
    path('api/delete_logs', views.api_delete_logs, name='api_delete_logs'),
    path('api/toggle_cancel', views.api_toggle_cancel, name='api_toggle_cancel'),
    path('api/edit_logs', views.api_edit_logs, name='api_edit_logs'),
]
