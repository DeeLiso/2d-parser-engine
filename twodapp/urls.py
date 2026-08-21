from django.contrib.auth import views as auth_views
from django.urls import path
from django.shortcuts import redirect
from django.views.static import serve
from django.conf import settings

from . import views

urlpatterns = [
    path('robots.txt', views.robots_txt, name='robots'),
    path('sw.js', lambda r: serve(r, 'sw.js', document_root=str(settings.BASE_DIR / 'twodapp' / 'static')), name='service_worker'),
    path('login/', auth_views.LoginView.as_view(template_name='twodapp/login.html'), name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('', lambda r: redirect('/login/'), name='home'),
    path('bet/', views.index, name='index'),
    path('records/', views.records_page, name='records'),
    path('bet/records/', views.bettor_records_page, name='bettor_records'),
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
    path('api/create_bettor', views.api_create_bettor, name='api_create_bettor'),
    path('api/list_bettors', views.api_list_bettors, name='api_list_bettors'),
    path('api/delete_bettor', views.api_delete_bettor, name='api_delete_bettor'),
    path('api/edit_bettor', views.api_edit_bettor, name='api_edit_bettor'),
    path('bet/login/', views.bettor_login_page, name='bettor_login'),
    path('bet/manage_bettors/', views.manage_bettors_page, name='manage_bettors'),
    path('api/bettor_login', views.api_bettor_login, name='api_bettor_login'),
    path('api/bettor_profile', views.api_bettor_profile, name='api_bettor_profile'),
]
