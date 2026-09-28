from django.contrib import admin

from .models import Booking, Category, City, Profile, Review, Service, WorkerProfile


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ('name', 'province', 'is_featured', 'featured_order')
    list_filter = ('province', 'is_featured')
    search_fields = ('name', 'province')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'sort_order')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'base_price', 'is_popular')
    list_filter = ('category', 'is_popular')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}


class WorkerInline(admin.StackedInline):
    model = WorkerProfile
    filter_horizontal = ('services', 'cities')
    extra = 0


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'phone', 'farm_city')
    list_filter = ('role',)
    search_fields = ('phone', 'user__first_name', 'user__last_name')
    inlines = [WorkerInline]


@admin.register(WorkerProfile)
class WorkerProfileAdmin(admin.ModelAdmin):
    list_display = ('profile', 'daily_wage', 'rating', 'is_verified', 'is_active')
    list_filter = ('is_verified', 'is_active', 'cities')
    search_fields = ('profile__user__first_name', 'profile__user__last_name', 'profile__phone')
    filter_horizontal = ('services', 'cities')
    actions = ('verify_workers',)

    @admin.action(description='تأیید هویت کارگران انتخاب‌شده')
    def verify_workers(self, request, queryset):
        queryset.update(is_verified=True)


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'farmer', 'worker', 'service', 'city', 'work_date', 'status')
    list_filter = ('status', 'city', 'service')
    search_fields = ('address', 'farmer__username', 'worker__profile__phone')


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('author_name', 'worker', 'rating', 'created_at')
    list_filter = ('rating',)
