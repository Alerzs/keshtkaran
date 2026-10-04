from functools import wraps
from urllib.parse import urlencode
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import (
    BookForm, FarmerProfileForm, LoginForm, OrderRequestForm, RegisterForm, ReviewForm, WorkerSettingsForm,
)
from .geo import city_centers
from .models import Booking, Category, City, Profile, Review, Service, WorkerProfile


def role_required(role):
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect(f"{reverse('login')}?{urlencode({'next': request.get_full_path()})}")
            profile = getattr(request.user, 'profile', None)
            if profile is None or profile.role != role:
                messages.error(request, {
                    Profile.FARMER: 'رزرو نیرو فقط برای صاحبان زمین امکان‌پذیر است.',
                    Profile.WORKER: 'این بخش مخصوص سرویس دهندگان است.',
                    Profile.ADMIN: 'این بخش مخصوص ادمین است.',
                }.get(role, 'به این بخش دسترسی ندارید.'))
                return redirect('home')
            return view(request, *args, **kwargs)
        return wrapper
    return decorator


def _safe_next(request, fallback='home'):
    target = request.POST.get('next') or request.GET.get('next') or ''
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return reverse(fallback)


def home(request):
    return render(request, 'marketplace/home.html', {
        'categories': Category.objects.all(),
        'popular_services': Service.objects.filter(is_popular=True).select_related('category'),
        'all_services': Service.objects.all(),
        'featured_workers': (
            WorkerProfile.objects.filter(is_active=True)
            .select_related('user__profile')
            .prefetch_related('services', 'cities')
            .order_by('-rating', '-jobs_done')[:4]
        ),
        'reviews': (
            Review.objects.select_related('worker__user__profile')
            .prefetch_related('worker__cities')[:6]
        ),
        'featured_cities': City.objects.filter(is_featured=True).order_by('featured_order'),
        'cities': City.objects.all(),
        'stats': {
            'workers': WorkerProfile.objects.filter(is_active=True).count(),
            'cities': City.objects.count(),
            'services': Service.objects.count(),
        },
    })


def service_list(request):
    categories = Category.objects.prefetch_related('services')
    return render(request, 'marketplace/services.html', {'categories': categories})


def category_detail(request, slug):
    category = get_object_or_404(Category.objects.prefetch_related('services'), slug=slug)
    return render(request, 'marketplace/category.html', {'category': category})


def order_service(request, slug):
    service = get_object_or_404(Service.objects.select_related('category'), slug=slug)
    initial = {}
    profile = getattr(request.user, 'profile', None) if request.user.is_authenticated else None
    if profile and profile.role == Profile.FARMER:
        if profile.farm_city_id:
            initial['city'] = profile.farm_city_id
        if profile.farm_address:
            initial['address'] = profile.farm_address
    form = OrderRequestForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        query = urlencode({
            'service': service.slug,
            'city': data['city'].pk,
            'address': data['address'],
            'date': data['work_date'].isoformat(),
            'area': data['land_area'] or '',
            'note': data['note'],
        })
        return redirect(f"{reverse('workers')}?{query}")
    return render(request, 'marketplace/order.html', {'service': service, 'form': form})


def _request_context(request):
    service_slug = request.GET.get('service', '').strip()
    query = request.GET.get('q', '').strip()
    city_raw = request.GET.get('city', '').strip()
    selected_service = None
    if service_slug:
        selected_service = Service.objects.filter(slug=service_slug).select_related('category').first()
    elif query:
        selected_service = Service.objects.filter(name=query).select_related('category').first()
    selected_city = City.objects.filter(pk=city_raw).first() if city_raw.isdigit() else None
    return {
        'q': query,
        'selected_service': selected_service,
        'selected_city': selected_city,
        'address': request.GET.get('address', '').strip(),
        'work_date': request.GET.get('date', '').strip(),
        'area': request.GET.get('area', '').strip(),
        'note': request.GET.get('note', '').strip(),
        'sort': request.GET.get('sort', 'rating'),
    }


def workers(request):
    ctx = _request_context(request)
    qs = (
        WorkerProfile.objects.filter(is_active=True)
        .select_related('user__profile')
        .prefetch_related('services', 'cities')
    )
    if ctx['selected_service']:
        qs = qs.filter(services=ctx['selected_service'])
    elif ctx['q']:
        qs = qs.filter(
            Q(user__name__icontains=ctx['q'])
            | Q(user__first_name__icontains=ctx['q'])
            | Q(user__last_name__icontains=ctx['q'])
            | Q(services__name__icontains=ctx['q'])
            | Q(bio__icontains=ctx['q'])
        )
    if ctx['selected_city']:
        qs = qs.filter(cities=ctx['selected_city'])

    sort = ctx['sort']
    if sort == 'wage':
        qs = qs.order_by('daily_wage', '-rating')
    elif sort == 'experience':
        qs = qs.order_by('-experience_years', '-rating')
    else:
        qs = qs.order_by('-rating', '-jobs_done')

    page_obj = Paginator(qs.distinct(), 8).get_page(request.GET.get('page'))
    ctx.update({
        'page_obj': page_obj,
        'services': Service.objects.select_related('category'),
        'cities': City.objects.all(),
    })
    return render(request, 'marketplace/workers.html', ctx)


def worker_detail(request, pk):
    worker = get_object_or_404(
        WorkerProfile.objects.select_related('user__profile').prefetch_related('services', 'cities', 'reviews'),
        pk=pk,
    )
    return render(request, 'marketplace/worker_detail.html', {
        'worker': worker,
        **_request_context(request),
    })


def _book_initial(request, worker):
    initial = {}
    slug = request.GET.get('service', '')
    if slug:
        service = worker.services.filter(slug=slug).first()
        if service:
            initial['service'] = service.pk
    city_raw = request.GET.get('city', '')
    if city_raw.isdigit() and worker.cities.filter(pk=city_raw).exists():
        initial['city'] = city_raw
    if request.GET.get('address'):
        initial['address'] = request.GET.get('address')
    if request.GET.get('date'):
        initial['work_date'] = request.GET.get('date')
    if request.GET.get('area'):
        initial['land_area'] = request.GET.get('area')
    if request.GET.get('note'):
        initial['note'] = request.GET.get('note')
    profile = request.user.profile
    if 'city' not in initial and profile.farm_city_id and worker.cities.filter(pk=profile.farm_city_id).exists():
        initial['city'] = profile.farm_city_id
    if 'address' not in initial and profile.farm_address:
        initial['address'] = profile.farm_address
    return initial


@role_required(Profile.FARMER)
def book(request, pk):
    if not request.user.profile.is_profile_complete:
        messages.info(request, 'قبل از رزرو، شهر و آدرس زمین را در پروفایل کامل کنید.')
        return redirect(f"{reverse('farmer_profile')}?{urlencode({'next': request.get_full_path()})}")
    worker = get_object_or_404(
        WorkerProfile.objects.select_related('user__profile').prefetch_related('services', 'cities'),
        pk=pk,
    )
    if not worker.is_active:
        messages.error(request, 'این سرویس دهنده فعلاً سفارش جدید نمی‌پذیرد.')
        return redirect('workers')
    if not worker.services.exists() or not worker.cities.exists():
        messages.error(request, 'پروفایل این سرویس دهنده هنوز کامل نشده است.')
        return redirect('workers')

    if request.method == 'POST':
        form = BookForm(request.POST, worker=worker)
        if form.is_valid():
            booking = form.save(request.user)
            messages.success(request, 'درخواست رزرو ثبت شد.')
            return redirect('bookings')
    else:
        form = BookForm(worker=worker, initial=_book_initial(request, worker))
    return render(request, 'marketplace/book.html', {'worker': worker, 'form': form})


@role_required(Profile.FARMER)
def bookings(request):
    items = (
        request.user.bookings
        .select_related('service', 'city', 'worker__user__profile', 'review')
        .order_by('-created_at')
    )
    return render(request, 'marketplace/bookings.html', {'bookings': items})


@require_POST
@role_required(Profile.FARMER)
def booking_cancel(request, pk):
    booking = get_object_or_404(Booking, pk=pk, farmer=request.user)
    if booking.status in (Booking.PENDING, Booking.CONFIRMED):
        booking.status = Booking.CANCELLED
        booking.save(update_fields=['status'])
        messages.success(request, 'رزرو لغو شد.')
    else:
        messages.error(request, 'این رزرو دیگر قابل لغو نیست.')
    return redirect('bookings')


@require_POST
@role_required(Profile.FARMER)
def booking_complete(request, pk):
    booking = get_object_or_404(
        Booking.objects.select_related('worker'),
        pk=pk,
        farmer=request.user,
        status=Booking.CONFIRMED,
    )
    booking.status = Booking.DONE
    booking.save(update_fields=['status'])
    WorkerProfile.objects.filter(pk=booking.worker_id).update(jobs_done=F('jobs_done') + 1)
    messages.success(request, 'اتمام کار ثبت شد. حالا می‌توانید نظر خود را بنویسید.')
    return redirect('bookings')


@require_POST
@role_required(Profile.FARMER)
def booking_review(request, pk):
    booking = get_object_or_404(Booking, pk=pk, farmer=request.user, status=Booking.DONE)
    if booking.existing_review:
        messages.error(request, 'برای این رزرو قبلاً نظر ثبت شده است.')
        return redirect('bookings')
    form = ReviewForm(request.POST)
    if form.is_valid():
        Review.objects.create(
            booking=booking,
            worker=booking.worker,
            author_name=request.user.get_full_name(),
            rating=form.cleaned_data['rating'],
            comment=form.cleaned_data['comment'].strip(),
        )
        booking.worker.refresh_rating()
        messages.success(request, 'نظر شما ثبت شد.')
    else:
        messages.error(request, 'امتیاز و متن نظر را کامل کنید.')
    return redirect('bookings')


@role_required(Profile.FARMER)
def farmer_profile(request):
    profile = request.user.profile
    form = FarmerProfileForm(request.POST or None, instance=profile)
    if request.method == 'POST' and form.is_valid():
        form.save()
        profile.refresh_from_db()
        messages.success(request, 'موقعیت زمین ذخیره شد.')
        if profile.is_profile_complete:
            return redirect(_safe_next(request))
    return render(request, 'marketplace/farmer_profile.html', {
        'form': form,
        'profile': profile,
        'city_centers': city_centers(),
    })


@role_required(Profile.ADMIN)
def admin_panel(request):
    selected = request.GET.get('status', '')
    valid = {value for value, _label in Booking.STATUS_CHOICES} | {'awaiting'}
    if selected not in valid:
        selected = ''
    jobs = (
        Booking.objects.select_related(
            'service', 'city', 'farmer__profile', 'worker__user__profile', 'confirmed_by',
        )
        .order_by('-created_at')
    )
    if selected == 'awaiting':
        jobs = jobs.filter(status=Booking.PENDING, admin_approved=False)
    elif selected == Booking.PENDING:
        jobs = jobs.filter(status=Booking.PENDING, admin_approved=True)
    elif selected:
        jobs = jobs.filter(status=selected)
    page_obj = Paginator(jobs, 10).get_page(request.GET.get('page'))
    counts = {row['status']: row['total'] for row in Booking.objects.values('status').annotate(total=Count('id'))}
    awaiting = Booking.objects.filter(status=Booking.PENDING, admin_approved=False).count()
    pending_ready = counts.get(Booking.PENDING, 0) - awaiting
    filters = [
        {'value': '', 'label': 'همه', 'count': sum(counts.values())},
        {'value': 'awaiting', 'label': 'منتظر تأیید صلاحیت', 'count': awaiting},
        {'value': Booking.PENDING, 'label': 'در انتظار پذیرش سرویس دهنده', 'count': pending_ready},
        *[
            {'value': value, 'label': label, 'count': counts.get(value, 0)}
            for value, label in Booking.STATUS_CHOICES
            if value != Booking.PENDING
        ],
    ]
    return render(request, 'marketplace/admin_panel.html', {
        'page_obj': page_obj,
        'filters': filters,
        'selected': selected,
    })


@require_POST
@role_required(Profile.ADMIN)
def admin_approve(request, pk):
    booking = get_object_or_404(Booking, pk=pk, status=Booking.PENDING, admin_approved=False)
    booking.confirmed_by = request.user
    booking.confirmed_at = timezone.now()
    if request.POST.get('action') == 'reject':
        booking.status = Booking.REJECTED
        booking.save(update_fields=['status', 'confirmed_by', 'confirmed_at'])
        messages.success(request, 'صلاحیت درخواست رد شد.')
    else:
        booking.admin_approved = True
        booking.save(update_fields=['admin_approved', 'confirmed_by', 'confirmed_at'])
        messages.success(request, 'صلاحیت درخواست تأیید شد و برای سرویس دهنده ارسال گردید.')
    return redirect('admin_panel')


@role_required(Profile.WORKER)
def worker_profile(request):
    worker, _ = WorkerProfile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        selected_services = {int(item) for item in request.POST.getlist('services') if item.isdigit()}
        selected_cities = {int(item) for item in request.POST.getlist('cities') if item.isdigit()}
    else:
        selected_services = set(worker.services.values_list('pk', flat=True))
        selected_cities = set(worker.cities.values_list('pk', flat=True))
    form = WorkerSettingsForm(request.POST or None, instance=worker)
    if request.method == 'POST' and form.is_valid():
        if not selected_services:
            form.add_error(None, 'حداقل یک حوزه کاری انتخاب کنید.')
        elif not selected_cities:
            form.add_error(None, 'حداقل یک شهر برای محل کار انتخاب کنید.')
        else:
            saved = form.save()
            saved.services.set(selected_services)
            saved.cities.set(selected_cities)
            messages.success(request, 'پروفایل کاری ذخیره شد. صاحبان زمین شما را در همین حوزه‌ها و شهرها می‌بینند.')
            return redirect('worker_profile')
    categories = Category.objects.prefetch_related('services')
    return render(request, 'marketplace/worker_profile.html', {
        'form': form,
        'worker': worker,
        'categories': categories,
        'cities': City.objects.all(),
        'selected_services': selected_services,
        'selected_cities': selected_cities,
    })


@role_required(Profile.WORKER)
def worker_jobs(request):
    worker = get_object_or_404(WorkerProfile, user=request.user)
    jobs = (
        worker.jobs.filter(admin_approved=True)
        .select_related('service', 'city', 'farmer__profile', 'review')
        .order_by('-created_at')
    )
    return render(request, 'marketplace/worker_jobs.html', {'jobs': jobs, 'worker': worker})


@require_POST
@role_required(Profile.WORKER)
def job_update(request, pk):
    worker = get_object_or_404(WorkerProfile, user=request.user)
    booking = get_object_or_404(Booking, pk=pk, worker=worker, admin_approved=True)
    action = request.POST.get('action')
    if action == 'confirm' and booking.status == Booking.PENDING:
        booking.status = Booking.CONFIRMED
        booking.save(update_fields=['status'])
        messages.success(request, 'درخواست را پذیرفتید. صاحب زمین حالا اطلاعات تماس شما را می‌بیند.')
    elif action == 'reject' and booking.status == Booking.PENDING:
        booking.status = Booking.REJECTED
        booking.save(update_fields=['status'])
        messages.success(request, 'درخواست رد شد.')
    else:
        messages.error(request, 'این تغییر وضعیت ممکن نیست.')
    return redirect('worker_jobs')


def register(request):
    if request.user.is_authenticated:
        return redirect('home')
    initial = {}
    if request.GET.get('role') in {Profile.FARMER, Profile.WORKER}:
        initial['role'] = request.GET.get('role')
    form = RegisterForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        if user.profile.role == Profile.WORKER:
            messages.info(request, 'حوزه کاری و شهرهای محل کار را در پروفایل مشخص کنید.')
            return redirect('worker_profile')
        messages.info(request, 'برای تکمیل پروفایل، شهر و آدرس زمین را ثبت کنید.')
        nxt = request.POST.get('next') or ''
        if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
            return redirect(f"{reverse('farmer_profile')}?{urlencode({'next': nxt})}")
        return redirect('farmer_profile')
    return render(request, 'marketplace/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = authenticate(
            request,
            username=form.cleaned_data['phone'],
            password=form.cleaned_data['password'],
        )
        if user is None:
            form.add_error(None, 'شماره موبایل یا رمز عبور نادرست است.')
        else:
            login(request, user)
            profile = getattr(user, 'profile', None)
            if profile and profile.role == Profile.WORKER:
                worker = getattr(profile, 'worker', None)
                if worker is None or not worker.services.exists():
                    messages.info(request, 'برای دیده شدن در پیشنهادها، حوزه کاری و محل کار را کامل کنید.')
                    return redirect('worker_profile')
            if profile and profile.role == Profile.FARMER and not profile.is_profile_complete:
                messages.info(request, 'پروفایل زمین هنوز کامل نیست.')
                nxt = request.POST.get('next') or request.GET.get('next') or ''
                if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
                    return redirect(f"{reverse('farmer_profile')}?{urlencode({'next': nxt})}")
                return redirect('farmer_profile')
            if profile and profile.role == Profile.ADMIN and not (request.POST.get('next') or request.GET.get('next')):
                return redirect('admin_panel')
            return redirect(_safe_next(request))
    return render(request, 'marketplace/login.html', {'form': form})


@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, 'از حساب خارج شدید.')
    return redirect('home')


def about(request):
    return render(request, 'marketplace/about.html')


def faq(request):
    return render(request, 'marketplace/faq.html')
