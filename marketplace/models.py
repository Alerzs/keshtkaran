from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg, Count
from django.urls import reverse
from django.utils import timezone


class City(models.Model):
    name = models.CharField('شهر', max_length=64, unique=True)
    province = models.CharField('استان', max_length=64)
    is_featured = models.BooleanField('شهر پربازدید', default=False)
    featured_order = models.PositiveSmallIntegerField('ترتیب نمایش', default=0)

    class Meta:
        verbose_name = 'شهر'
        verbose_name_plural = 'شهرها'
        ordering = ['province', 'name']

    def __str__(self):
        return f'{self.name} ({self.province})'


class Category(models.Model):
    name = models.CharField('نام', max_length=80)
    slug = models.SlugField(unique=True)
    description = models.CharField('توضیح', max_length=180)
    icon_bg = models.CharField(max_length=80, default='bg-teal-100 text-teal-700')
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = 'دسته‌بندی'
        verbose_name_plural = 'دسته‌بندی‌ها'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('category', args=[self.slug])


class Service(models.Model):
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name='services', verbose_name='دسته',
    )
    name = models.CharField('نام خدمت', max_length=120)
    slug = models.SlugField(unique=True)
    description = models.CharField('توضیح', max_length=220)
    base_price = models.PositiveIntegerField('شروع قیمت روزانه', default=0)
    gradient = models.CharField(max_length=80, blank=True)
    is_popular = models.BooleanField('پرتقاضا', default=False)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = 'خدمت'
        verbose_name_plural = 'خدمات'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('order', args=[self.slug])


class Profile(models.Model):
    FARMER = 'farmer'
    WORKER = 'worker'
    ADMIN = 'admin'
    ROLE_CHOICES = [
        (FARMER, 'صاحب زمین'),
        (WORKER, 'کارگر'),
        (ADMIN, 'ادمین'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField('نقش', max_length=10, choices=ROLE_CHOICES)
    phone = models.CharField('موبایل', max_length=11)
    farm_city = models.ForeignKey(
        City, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='farmers', verbose_name='شهر زمین',
    )
    farm_address = models.CharField('آدرس زمین', max_length=255, blank=True)
    farm_latitude = models.DecimalField(
        'عرض جغرافیایی زمین', max_digits=9, decimal_places=6, null=True, blank=True,
    )
    farm_longitude = models.DecimalField(
        'طول جغرافیایی زمین', max_digits=9, decimal_places=6, null=True, blank=True,
    )

    class Meta:
        verbose_name = 'پروفایل'
        verbose_name_plural = 'پروفایل‌ها'

    def __str__(self):
        return f'{self.user.get_full_name()} — {self.get_role_display()}'

    def clean(self):
        super().clean()
        lat = self.farm_latitude
        lng = self.farm_longitude
        if lat is None and lng is None:
            return
        if lat is None or lng is None:
            raise ValidationError('برای ثبت موقعیت روی نقشه، عرض و طول جغرافیایی را با هم مشخص کنید.')
        if lat < Decimal('24') or lat > Decimal('40'):
            raise ValidationError({'farm_latitude': 'عرض جغرافیایی باید داخل محدوده ایران باشد.'})
        if lng < Decimal('44') or lng > Decimal('64'):
            raise ValidationError({'farm_longitude': 'طول جغرافیایی باید داخل محدوده ایران باشد.'})

    @property
    def has_farm_location(self):
        return self.farm_latitude is not None and self.farm_longitude is not None

    @property
    def initials(self):
        first = (self.user.first_name or 'ک')[:1]
        last = (self.user.last_name or '')[:1]
        return f'{first}{last}'

    @property
    def avatar_class(self):
        palette = [
            'bg-teal-600',
            'bg-emerald-600',
            'bg-cyan-700',
            'bg-lime-700',
            'bg-amber-600',
            'bg-orange-600',
            'bg-sky-700',
            'bg-green-700',
        ]
        return palette[(self.pk or 0) % len(palette)]

    def completion_steps(self):
        user = self.user
        if self.role == self.FARMER:
            pairs = [
                ('نام و نام خانوادگی', bool(user.first_name and user.last_name)),
                ('شماره موبایل', bool(self.phone)),
                ('شهر زمین', bool(self.farm_city_id)),
                ('آدرس دقیق زمین', len((self.farm_address or '').strip()) >= 8),
            ]
        elif self.role == self.WORKER:
            worker = getattr(self, 'worker', None)
            pairs = [
                ('نام و نام خانوادگی', bool(user.first_name and user.last_name)),
                ('شماره موبایل', bool(self.phone)),
                ('توضیح تجربه کاری', bool(worker and len((worker.bio or '').strip()) >= 10)),
                ('حوزه کاری', bool(worker and worker.services.exists())),
                ('شهرهای محل کار', bool(worker and worker.cities.exists())),
            ]
        else:
            pairs = [
                ('نام و نام خانوادگی', bool(user.first_name and user.last_name)),
                ('شماره موبایل', bool(self.phone)),
            ]
        return [{'label': label, 'done': done} for label, done in pairs]

    @property
    def completion_percent(self):
        steps = self.completion_steps()
        if not steps:
            return 100
        done = sum(1 for step in steps if step['done'])
        return round(100 * done / len(steps))

    @property
    def is_profile_complete(self):
        return self.completion_percent == 100


class WorkerProfile(models.Model):
    profile = models.OneToOneField(
        Profile, on_delete=models.CASCADE, related_name='worker', verbose_name='کاربر',
    )
    bio = models.TextField('درباره تجربه کاری', blank=True)
    experience_years = models.PositiveSmallIntegerField(
        'سابقه (سال)', default=0, validators=[MaxValueValidator(60)],
    )
    daily_wage = models.PositiveIntegerField('دستمزد روزانه (تومان)', default=0)
    rating = models.DecimalField('امتیاز', max_digits=2, decimal_places=1, default=0)
    review_count = models.PositiveIntegerField('تعداد نظر', default=0)
    jobs_done = models.PositiveIntegerField('کارهای انجام‌شده', default=0)
    is_verified = models.BooleanField('هویت تأیید شده', default=False)
    is_active = models.BooleanField('آماده دریافت کار', default=True)
    services = models.ManyToManyField(Service, blank=True, related_name='workers', verbose_name='حوزه کاری')
    cities = models.ManyToManyField(City, blank=True, related_name='workers', verbose_name='محل کار')

    class Meta:
        verbose_name = 'پروفایل کارگر'
        verbose_name_plural = 'پروفایل کارگران'
        ordering = ['-rating', '-jobs_done']

    def __str__(self):
        return self.profile.user.get_full_name() or self.profile.phone

    def refresh_rating(self):
        data = self.reviews.aggregate(avg=Avg('rating'), total=Count('id'))
        average = data['avg'] or 0
        self.rating = Decimal(str(round(average, 1)))
        self.review_count = data['total'] or 0
        self.save(update_fields=['rating', 'review_count'])


class Booking(models.Model):
    PENDING = 'pending'
    CONFIRMED = 'confirmed'
    REPORTED = 'reported'
    REJECTED = 'rejected'
    CANCELLED = 'cancelled'
    DONE = 'done'
    STATUS_CHOICES = [
        (PENDING, 'در انتظار پذیرش'),
        (CONFIRMED, 'پذیرفته شده'),
        (REPORTED, 'اعلام انجام، منتظر ادمین'),
        (REJECTED, 'رد شده'),
        (CANCELLED, 'لغو شده'),
        (DONE, 'انجام تأیید شد'),
    ]
    STATUS_CLASSES = {
        PENDING: 'bg-amber-100 text-amber-800',
        CONFIRMED: 'bg-sky-100 text-sky-800',
        REPORTED: 'bg-violet-100 text-violet-800',
        REJECTED: 'bg-rose-100 text-rose-700',
        CANCELLED: 'bg-slate-100 text-slate-600',
        DONE: 'bg-emerald-100 text-emerald-800',
    }

    farmer = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='bookings', verbose_name='صاحب زمین',
    )
    worker = models.ForeignKey(
        WorkerProfile, on_delete=models.CASCADE, related_name='jobs', verbose_name='کارگر',
    )
    service = models.ForeignKey(
        Service, on_delete=models.PROTECT, related_name='bookings', verbose_name='خدمت',
    )
    city = models.ForeignKey(City, on_delete=models.PROTECT, verbose_name='شهر')
    address = models.CharField('آدرس زمین', max_length=255)
    work_date = models.DateField('تاریخ مراجعه')
    land_area = models.DecimalField(
        'مساحت (هکتار)', max_digits=8, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    note = models.TextField('توضیح', blank=True)
    wage = models.PositiveIntegerField('دستمزد روزانه در زمان رزرو', default=0)
    status = models.CharField('وضعیت', max_length=12, choices=STATUS_CHOICES, default=PENDING)
    reported_at = models.DateTimeField('زمان اعلام انجام', null=True, blank=True)
    confirmed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='approved_jobs', verbose_name='ادمین تأییدکننده',
    )
    confirmed_at = models.DateTimeField('زمان تأیید ادمین', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'رزرو'
        verbose_name_plural = 'رزروها'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.service} — {self.work_date}'

    def progress_stages(self):
        labels = ['ثبت رزرو', 'پذیرش کارگر', 'اعلام انجام', 'تأیید ادمین']
        rank = {
            self.PENDING: 1,
            self.CONFIRMED: 2,
            self.REPORTED: 3,
            self.DONE: 4,
        }
        current = rank.get(self.status, 1)
        failed = self.status in (self.REJECTED, self.CANCELLED)
        stages = []
        for index, label in enumerate(labels, start=1):
            if self.status == self.DONE:
                state = 'done'
            elif failed:
                state = 'done' if index == 1 else 'muted'
            elif index < current:
                state = 'done'
            elif index == current:
                state = 'current'
            else:
                state = 'upcoming'
            stages.append({'label': label, 'state': state})
        return stages

    @property
    def status_classes(self):
        return self.STATUS_CLASSES.get(self.status, 'bg-slate-100 text-slate-600')

    @property
    def existing_review(self):
        try:
            return self.review
        except Review.DoesNotExist:
            return None


class Review(models.Model):
    booking = models.OneToOneField(
        Booking, null=True, blank=True, on_delete=models.CASCADE, related_name='review',
    )
    worker = models.ForeignKey(WorkerProfile, on_delete=models.CASCADE, related_name='reviews')
    author_name = models.CharField(max_length=80)
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'نظر'
        verbose_name_plural = 'نظرها'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.author_name} — {self.rating}'
