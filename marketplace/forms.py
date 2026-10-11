import re
from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone

from .models import Booking, City, Profile, Service, WorkerProfile
from .utils import normalize_phone

INPUT_CLASS = (
    'w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none '
    'transition focus:border-teal-500 focus:bg-white focus:ring-4 focus:ring-teal-100'
)


class RegisterForm(forms.Form):
    first_name = forms.CharField(label='نام', max_length=50)
    last_name = forms.CharField(label='نام خانوادگی', max_length=50)
    phone = forms.CharField(label='شماره موبایل', max_length=20)
    password = forms.CharField(label='رمز عبور', widget=forms.PasswordInput)
    password2 = forms.CharField(label='تکرار رمز عبور', widget=forms.PasswordInput)
    role = forms.ChoiceField(
        label='نقش',
        choices=[item for item in Profile.ROLE_CHOICES if item[0] != Profile.ADMIN],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name != 'role':
                field.widget.attrs['class'] = INPUT_CLASS
        self.fields['phone'].widget.attrs.update({'dir': 'ltr', 'inputmode': 'numeric', 'placeholder': '0912...'})

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data['phone'])
        if not re.fullmatch(r'09\d{9}', phone):
            raise forms.ValidationError('شماره موبایل را با ۰۹ و ۱۱ رقم وارد کنید.')
        if get_user_model().objects.filter(username=phone).exists():
            raise forms.ValidationError('این شماره قبلاً ثبت شده است.')
        return phone

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get('password')
        if password:
            validate_password(password)
        if password and cleaned.get('password2') and password != cleaned.get('password2'):
            self.add_error('password2', 'تکرار رمز عبور یکسان نیست.')
        return cleaned

    def save(self):
        data = self.cleaned_data
        first_name = data['first_name'].strip()
        last_name = data['last_name'].strip()
        user = get_user_model().objects.create_user(
            username=data['phone'],
            password=data['password'],
            first_name=first_name,
            last_name=last_name,
            name=f'{first_name} {last_name}'.strip(),
        )
        Profile.objects.create(user=user, role=data['role'], phone=data['phone'])
        if data['role'] == Profile.WORKER:
            WorkerProfile.objects.create(user=user)
        return user


class AdminAccountForm(forms.Form):
    role = forms.ChoiceField(
        label='نقش',
        choices=[item for item in Profile.ROLE_CHOICES if item[0] != Profile.ADMIN],
        initial=Profile.FARMER,
    )
    name = forms.CharField(label='نام', max_length=150)
    username = forms.CharField(label='نام کاربری', max_length=20)
    password = forms.CharField(label='رمز عبور', widget=forms.PasswordInput)
    password2 = forms.CharField(label='تکرار رمز عبور', required=False, widget=forms.PasswordInput)
    bio = forms.CharField(
        label='درباره تجربه کاری', required=False, widget=forms.Textarea(attrs={'rows': 4}),
    )
    experience_years = forms.IntegerField(label='سابقه کار (سال)', required=False, min_value=0, max_value=60)
    daily_wage = forms.IntegerField(label='دستمزد روزانه (تومان)', required=False, min_value=0)
    is_active = forms.BooleanField(label='آماده دریافت کار هستم', required=False, initial=True)
    farm_city = forms.ModelChoiceField(
        label='شهر زمین', queryset=City.objects.all(), required=False, empty_label='شهر زمین را انتخاب کنید',
    )
    farm_address = forms.CharField(
        label='آدرس دقیق زمین', required=False, max_length=255, widget=forms.Textarea(attrs={'rows': 3}),
    )
    farm_latitude = forms.DecimalField(
        label='عرض جغرافیایی', required=False, max_digits=9, decimal_places=6, widget=forms.HiddenInput,
    )
    farm_longitude = forms.DecimalField(
        label='طول جغرافیایی', required=False, max_digits=9, decimal_places=6, widget=forms.HiddenInput,
    )

    worker_fields = ('bio', 'experience_years', 'daily_wage', 'is_active')
    farmer_fields = ('farm_city', 'farm_address', 'farm_latitude', 'farm_longitude')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name in {'role', 'is_active', 'farm_latitude', 'farm_longitude'}:
                continue
            field.widget.attrs['class'] = INPUT_CLASS
        self.fields['username'].widget.attrs.update({
            'dir': 'ltr', 'inputmode': 'numeric', 'placeholder': '0912...',
        })
        self.fields['bio'].widget.attrs['class'] += ' min-h-32 resize-y'
        self.fields['farm_address'].widget.attrs['class'] += ' min-h-28 resize-y'
        self.fields['farm_address'].widget.attrs['placeholder'] = 'روستا، جاده، نام قطعه یا نشانه محلی'
        self.fields['experience_years'].widget.attrs.update({'dir': 'ltr', 'min': '0', 'max': '60'})
        self.fields['daily_wage'].widget.attrs.update({'dir': 'ltr', 'min': '0'})
        self.fields['is_active'].widget.attrs['class'] = 'h-5 w-5 accent-teal-600'

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if not name:
            raise forms.ValidationError('نام را وارد کنید.')
        return name

    def clean_username(self):
        phone = normalize_phone(self.cleaned_data['username'])
        if not re.fullmatch(r'09\d{9}', phone):
            raise forms.ValidationError('نام کاربری همان شماره موبایل است و باید با ۰۹ و ۱۱ رقم وارد شود.')
        if get_user_model().objects.filter(username=phone).exists():
            raise forms.ValidationError('این نام کاربری قبلاً ثبت شده است.')
        return phone

    def selected_pks(self, key):
        if not self.is_bound:
            return set()
        return {int(item) for item in self.data.getlist(key) if str(item).isdigit()}

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get('password')
        if password:
            validate_password(password)
        if password and cleaned.get('password2') and password != cleaned.get('password2'):
            self.add_error('password2', 'تکرار رمز عبور یکسان نیست.')
        role = cleaned.get('role')
        if role == Profile.WORKER:
            for name in self.farmer_fields:
                self.errors.pop(name, None)
            self._clean_worker(cleaned)
        elif role == Profile.FARMER:
            for name in self.worker_fields:
                self.errors.pop(name, None)
            self._clean_farmer(cleaned)
        return cleaned

    def _clean_worker(self, cleaned):
        cleaned['bio'] = (cleaned.get('bio') or '').strip()
        service_ids = self.selected_pks('services')
        city_ids = self.selected_pks('cities')
        services = list(Service.objects.filter(pk__in=service_ids))
        cities = list(City.objects.filter(pk__in=city_ids))
        if len(services) != len(service_ids):
            self.add_error(None, 'حوزه کاری انتخاب‌شده معتبر نیست.')
        if len(cities) != len(city_ids):
            self.add_error(None, 'شهر محل کار انتخاب‌شده معتبر نیست.')
        cleaned['services'] = services
        cleaned['cities'] = cities
        if cleaned.get('experience_years') is None:
            cleaned['experience_years'] = 0
        if cleaned.get('daily_wage') is None:
            cleaned['daily_wage'] = 0

    def _clean_farmer(self, cleaned):
        cleaned['farm_address'] = (cleaned.get('farm_address') or '').strip()
        lat = cleaned.get('farm_latitude')
        lng = cleaned.get('farm_longitude')
        if lat is None and lng is None:
            return
        if lat is None or lng is None:
            self.add_error(None, 'برای ثبت موقعیت روی نقشه، عرض و طول جغرافیایی را با هم مشخص کنید.')
            return
        if lat < Decimal('24') or lat > Decimal('40'):
            self.add_error('farm_latitude', 'عرض جغرافیایی باید داخل محدوده ایران باشد.')
        if lng < Decimal('44') or lng > Decimal('64'):
            self.add_error('farm_longitude', 'طول جغرافیایی باید داخل محدوده ایران باشد.')

    @transaction.atomic
    def save(self):
        data = self.cleaned_data
        name = data['name']
        parts = name.split()
        user = get_user_model().objects.create_user(
            username=data['username'],
            password=data['password'],
            first_name=parts[0],
            last_name=' '.join(parts[1:]),
            name=name,
        )
        profile = Profile.objects.create(user=user, role=data['role'], phone=data['username'])
        if data['role'] == Profile.WORKER:
            worker = WorkerProfile.objects.create(
                user=user,
                bio=data['bio'],
                experience_years=data['experience_years'],
                daily_wage=data['daily_wage'],
                is_active=bool(data.get('is_active')),
            )
            worker.services.set(data['services'])
            worker.cities.set(data['cities'])
        else:
            profile.farm_city = data['farm_city']
            profile.farm_address = data['farm_address']
            profile.farm_latitude = data.get('farm_latitude')
            profile.farm_longitude = data.get('farm_longitude')
            profile.save()
        return user


class LoginForm(forms.Form):
    phone = forms.CharField(label='شماره موبایل')
    password = forms.CharField(label='رمز عبور', widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CLASS
        self.fields['phone'].widget.attrs.update({'dir': 'ltr', 'inputmode': 'numeric', 'placeholder': '0912...'})

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data['phone'])
        if not re.fullmatch(r'09\d{9}', phone):
            raise forms.ValidationError('شماره موبایل معتبر نیست.')
        return phone


class OrderRequestForm(forms.Form):
    city = forms.ModelChoiceField(label='شهر محل زمین', queryset=City.objects.all(), empty_label='شهر را انتخاب کنید')
    address = forms.CharField(label='آدرس دقیق زمین', max_length=255)
    work_date = forms.DateField(
        label='تاریخ مراجعه',
        widget=forms.DateInput(attrs={'type': 'date'}),
        error_messages={'invalid': 'تاریخ معتبر نیست.'},
    )
    land_area = forms.DecimalField(
        label='مساحت زمین (هکتار)', required=False, min_value=0, max_value=10000, decimal_places=2,
    )
    note = forms.CharField(label='توضیح کار', required=False, widget=forms.Textarea(attrs={'rows': 4}), max_length=500)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs['class'] = INPUT_CLASS
        self.fields['work_date'].widget.attrs.update({
            'dir': 'ltr',
            'min': timezone.localdate().isoformat(),
        })
        self.fields['land_area'].widget.attrs.update({'dir': 'ltr', 'placeholder': 'مثلاً ۲.۵', 'step': '0.1'})
        self.fields['address'].widget.attrs['placeholder'] = 'روستا، جاده، نام قطعه یا نشانه محلی'
        self.fields['note'].widget.attrs['placeholder'] = 'نوع محصول، ساعت حضور، ابزار موردنیاز...'

    def clean_address(self):
        address = self.cleaned_data['address'].strip()
        if len(address) < 8:
            raise forms.ValidationError('آدرس را دقیق‌تر بنویسید تا سرویس دهنده زمین را پیدا کند.')
        return address

    def clean_work_date(self):
        value = self.cleaned_data['work_date']
        if value < timezone.localdate():
            raise forms.ValidationError('تاریخ نمی‌تواند در گذشته باشد.')
        return value


class BookForm(OrderRequestForm):
    service = forms.ModelChoiceField(label='نوع خدمت', queryset=Service.objects.none(), empty_label='خدمت را انتخاب کنید')

    def __init__(self, *args, worker, **kwargs):
        self.worker = worker
        super().__init__(*args, **kwargs)
        self.fields['service'].queryset = worker.services.all()
        self.fields['city'].queryset = worker.cities.all()
        self.fields['service'].widget.attrs['class'] = INPUT_CLASS
        self.order_fields(['service', 'city', 'address', 'work_date', 'land_area', 'note'])

    def clean(self):
        cleaned = super().clean()
        service = cleaned.get('service')
        city = cleaned.get('city')
        if service and not self.worker.services.filter(pk=service.pk).exists():
            self.add_error('service', 'این سرویس دهنده در حوزه انتخاب‌شده فعالیت نمی‌کند.')
        if city and not self.worker.cities.filter(pk=city.pk).exists():
            self.add_error('city', 'این سرویس دهنده در شهر انتخاب‌شده کار نمی‌کند.')
        return cleaned

    def save(self, farmer):
        data = self.cleaned_data
        return Booking.objects.create(
            farmer=farmer,
            worker=self.worker,
            service=data['service'],
            city=data['city'],
            address=data['address'],
            work_date=data['work_date'],
            land_area=data.get('land_area') or None,
            note=(data.get('note') or '').strip(),
            wage=self.worker.daily_wage,
        )


class FarmerProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['farm_city', 'farm_address', 'farm_latitude', 'farm_longitude']
        labels = {
            'farm_city': 'شهر زمین',
            'farm_address': 'آدرس دقیق زمین',
            'farm_latitude': 'عرض جغرافیایی',
            'farm_longitude': 'طول جغرافیایی',
        }
        widgets = {
            'farm_address': forms.Textarea(attrs={'rows': 3}),
            'farm_latitude': forms.HiddenInput,
            'farm_longitude': forms.HiddenInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['farm_city'].queryset = City.objects.all()
        self.fields['farm_city'].empty_label = 'شهر زمین را انتخاب کنید'
        self.fields['farm_city'].required = True
        self.fields['farm_address'].required = True
        for name, field in self.fields.items():
            if name not in ('farm_latitude', 'farm_longitude'):
                field.widget.attrs['class'] = INPUT_CLASS
        self.fields['farm_address'].widget.attrs['placeholder'] = 'روستا، جاده، نام قطعه یا نشانه محلی'
        self.fields['farm_address'].widget.attrs['class'] += ' min-h-28 resize-y'
        self.fields['farm_latitude'].required = False
        self.fields['farm_longitude'].required = False

    def clean_farm_address(self):
        address = self.cleaned_data['farm_address'].strip()
        if len(address) < 8:
            raise forms.ValidationError('آدرس را دقیق‌تر بنویسید تا سرویس دهنده زمین را پیدا کند.')
        return address


class WorkerSettingsForm(forms.ModelForm):
    class Meta:
        model = WorkerProfile
        fields = ['bio', 'experience_years', 'daily_wage', 'is_active']
        labels = {
            'bio': 'درباره تجربه کاری',
            'experience_years': 'سابقه کار (سال)',
            'daily_wage': 'دستمزد روزانه (تومان)',
            'is_active': 'آماده دریافت کار هستم',
        }
        help_texts = {
            'daily_wage': 'صفر یعنی دستمزد توافقی است.',
            'bio': 'بگویید در چه محصولی و چه کاری مهارت دارید.',
        }
        widgets = {'bio': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name != 'is_active':
                field.widget.attrs['class'] = INPUT_CLASS
        self.fields['bio'].widget.attrs['minlength'] = '10'
        self.fields['bio'].widget.attrs['class'] += ' min-h-32 resize-y'
        self.fields['daily_wage'].widget.attrs.update({'dir': 'ltr', 'min': '0'})
        self.fields['experience_years'].widget.attrs.update({'dir': 'ltr', 'min': '0', 'max': '60'})
        self.fields['is_active'].widget.attrs['class'] = 'h-5 w-5 accent-teal-600'

    def clean_bio(self):
        bio = self.cleaned_data['bio'].strip()
        if len(bio) < 10:
            raise forms.ValidationError('حداقل ۱۰ نویسه درباره تجربه کاری بنویسید.')
        return bio


class ReviewForm(forms.Form):
    rating = forms.IntegerField(min_value=1, max_value=5, label='امتیاز')
    comment = forms.CharField(label='نظر', max_length=500, widget=forms.Textarea(attrs={'rows': 3, 'class': INPUT_CLASS}))
