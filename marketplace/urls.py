from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('services/', views.service_list, name='services'),
    path('services/<slug:slug>/', views.category_detail, name='category'),
    path('order/<slug:slug>/', views.order_service, name='order'),
    path('workers/', views.workers, name='workers'),
    path('workers/<int:pk>/', views.worker_detail, name='worker_detail'),
    path('book/<int:pk>/', views.book, name='book'),
    path('profile/', views.farmer_profile, name='farmer_profile'),
    path('panel/', views.admin_panel, name='admin_panel'),
    path('panel/<int:pk>/confirm/', views.admin_confirm_done, name='admin_confirm_done'),
    path('bookings/', views.bookings, name='bookings'),
    path('bookings/<int:pk>/cancel/', views.booking_cancel, name='booking_cancel'),
    path('bookings/<int:pk>/review/', views.booking_review, name='booking_review'),
    path('worker/profile/', views.worker_profile, name='worker_profile'),
    path('worker/jobs/', views.worker_jobs, name='worker_jobs'),
    path('worker/jobs/<int:pk>/', views.job_update, name='job_update'),
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('about/', views.about, name='about'),
    path('faq/', views.faq, name='faq'),
]
