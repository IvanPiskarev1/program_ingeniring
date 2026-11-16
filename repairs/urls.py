from django.urls import path
from . import views, public, report_views
urlpatterns = [
    path('favicon.ico', views.favicon, name='favicon'),
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('orders/', views.order_list, name='orders'),
    path('orders/new/', views.order_new, name='intake'),
    path('orders/<int:pk>/', views.order_detail, name='order_detail'),
    path('orders/<int:pk>/action/<str:action>/', views.order_action, name='order_action'),
    path('orders/<int:pk>/print/', public.print_order, name='print_order'),
    path('orders/<int:pk>/qr/', public.qr_image, name='qr'),
    path('clients/', views.clients, name='clients'),
    path('clients/<int:pk>/', views.client_detail, name='client'),
    path('devices/<int:pk>/', views.device_detail, name='device'),
    path('masters/', views.masters, name='masters'),
    path('reports/', report_views.reports, name='reports'),
    path('track/', public.track, name='track'),
    path('track/<str:token>/', public.status_page, name='public_status'),
    path('api/orders/', public.order_api, name='orders_api'),
    path('api/orders/<int:pk>/', public.order_api, name='order_api'),
    path('api/public/status/<str:token>/', public.status_api, name='public_api'),
]
