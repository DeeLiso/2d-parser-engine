from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('records/', views.records_page, name='records'),
    path('ledger/', views.ledger_page, name='ledger'),
    path('api/parse', views.api_parse, name='api_parse'),
    path('api/set_global_limit', views.api_set_global_limit, name='api_set_global_limit'),
    path('api/set_specific_limit', views.api_set_specific_limit, name='api_set_specific_limit'),
    path('api/delete_specific_limit', views.api_delete_specific_limit, name='api_delete_specific_limit'),
    path('api/save_meta', views.api_save_meta, name='api_save_meta'),
    path('api/clear_all', views.api_clear_all, name='api_clear_all'),
]
