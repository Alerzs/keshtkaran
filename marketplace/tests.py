from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from marketplace.models import Booking, City, Service


class MarketplaceFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed')

    def test_home_lists_services(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'کشت‌کاران')
        self.assertContains(response, 'برداشت گندم و جو')

    def test_suggests_workers_by_service_and_city(self):
        city = City.objects.get(name='مشهد')
        response = self.client.get(reverse('workers'), {'service': 'wheat-harvest', 'city': city.pk})
        self.assertContains(response, 'رضا محمدی')
        self.assertContains(response, 'مجید کاظمی')
        self.assertNotContains(response, 'حسین کریمی')

    def test_order_form_redirects_to_matching_workers(self):
        city = City.objects.get(name='شیراز')
        response = self.client.post(reverse('order', args=['spraying']), {
            'city': city.pk,
            'address': 'جاده مرودشت، قطعه جنوبی باغ',
            'work_date': (timezone.localdate() + timedelta(days=2)).isoformat(),
            'land_area': '1.5',
            'note': 'سمپاشی مرکبات',
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/workers/', response['Location'])
        self.assertIn('service=spraying', response['Location'])

    def test_farmer_can_book_matching_worker(self):
        self.client.login(username='09121111111', password='demo1234')
        city = City.objects.get(name='مشهد')
        profile = User.objects.get(username='09121111111').profile
        profile.farm_city = city
        profile.farm_address = 'جاده کلات، کیلومتر ۱۲، قطعه نمونه'
        profile.save()
        service = Service.objects.get(slug='wheat-harvest')
        worker = User.objects.get(username='09130000001').profile.worker
        response = self.client.post(reverse('book', args=[worker.pk]), {
            'service': service.pk,
            'city': city.pk,
            'address': 'جاده کلات، کیلومتر ۱۲',
            'work_date': (timezone.localdate() + timedelta(days=3)).isoformat(),
            'land_area': '2.5',
            'note': 'برداشت قطعه شمالی',
        })
        self.assertRedirects(response, reverse('bookings'))
        booking = Booking.objects.get()
        self.assertEqual(booking.status, Booking.PENDING)
        self.assertEqual(booking.worker, worker)

    def test_worker_cannot_book(self):
        self.client.login(username='09130000001', password='demo1234')
        other = User.objects.get(username='09130000002').profile.worker
        response = self.client.get(reverse('book', args=[other.pk]))
        self.assertRedirects(response, reverse('home'))

    def test_worker_list_renders_pages(self):
        response = self.client.get(reverse('workers'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'بعدی')

    def test_incomplete_farmer_is_sent_to_profile(self):
        self.client.login(username='09121111111', password='demo1234')
        worker = User.objects.get(username='09130000001').profile.worker
        response = self.client.get(reverse('book', args=[worker.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('farmer_profile'), response['Location'])
        profile = User.objects.get(username='09121111111').profile
        self.assertEqual(profile.completion_percent, 50)
        response = self.client.post(reverse('farmer_profile'), {
            'farm_city': City.objects.get(name='مشهد').pk,
            'farm_address': 'جاده کلات، کیلومتر ۱۲، قطعه نمونه',
        })
        self.assertRedirects(response, reverse('home'))
        profile.refresh_from_db()
        self.assertEqual(profile.completion_percent, 100)

    def test_admin_confirms_finished_work(self):
        farmer = User.objects.get(username='09121111111')
        city = City.objects.get(name='مشهد')
        farmer.profile.farm_city = city
        farmer.profile.farm_address = 'جاده کلات، کیلومتر ۱۲، قطعه نمونه'
        farmer.profile.save()
        worker_profile = User.objects.get(username='09130000001').profile.worker
        jobs_before = worker_profile.jobs_done
        self.client.login(username='09121111111', password='demo1234')
        self.client.post(reverse('book', args=[worker_profile.pk]), {
            'service': Service.objects.get(slug='wheat-harvest').pk,
            'city': city.pk,
            'address': 'جاده کلات، کیلومتر ۱۲',
            'work_date': (timezone.localdate() + timedelta(days=4)).isoformat(),
            'note': 'برداشت آزمایشی',
        })
        booking = Booking.objects.get()
        self.client.logout()
        self.client.login(username='09130000001', password='demo1234')
        self.client.post(reverse('job_update', args=[booking.pk]), {'action': 'confirm'})
        self.client.post(reverse('job_update', args=[booking.pk]), {'action': 'report'})
        booking.refresh_from_db()
        worker_profile.refresh_from_db()
        self.assertEqual(booking.status, Booking.REPORTED)
        self.assertEqual(worker_profile.jobs_done, jobs_before)
        self.client.logout()
        self.client.login(username='09124444444', password='demo1234')
        panel = self.client.get(reverse('admin_panel'))
        self.assertContains(panel, 'رضا محمدی')
        self.assertContains(panel, 'اعلام انجام')
        self.client.post(reverse('admin_confirm_done', args=[booking.pk]))
        booking.refresh_from_db()
        worker_profile.refresh_from_db()
        self.assertEqual(booking.status, Booking.DONE)
        self.assertEqual(worker_profile.jobs_done, jobs_before + 1)
        self.assertEqual(booking.confirmed_by.username, '09124444444')

    def test_farmer_can_save_optional_map_location(self):
        self.client.login(username='09121111111', password='demo1234')
        city = City.objects.get(name='مشهد')
        response = self.client.post(reverse('farmer_profile'), {
            'farm_city': city.pk,
            'farm_address': 'جاده کلات، کیلومتر ۱۲، قطعه نمونه',
            'farm_latitude': '36.297200',
            'farm_longitude': '59.606700',
        })
        self.assertRedirects(response, reverse('home'))
        profile = User.objects.get(username='09121111111').profile
        self.assertTrue(profile.has_farm_location)
        self.assertEqual(profile.farm_latitude, Decimal('36.297200'))
        self.assertEqual(profile.farm_longitude, Decimal('59.606700'))
        self.assertEqual(profile.completion_percent, 100)
        page = self.client.get(reverse('farmer_profile'))
        self.assertContains(page, 'id="farm-map"')
        self.assertContains(page, '36.297200')

    def test_farmer_map_location_must_stay_inside_iran(self):
        self.client.login(username='09121111111', password='demo1234')
        city = City.objects.get(name='مشهد')
        response = self.client.post(reverse('farmer_profile'), {
            'farm_city': city.pk,
            'farm_address': 'جاده کلات، کیلومتر ۱۲، قطعه نمونه',
            'farm_latitude': '48.800000',
            'farm_longitude': '2.300000',
        })
        self.assertEqual(response.status_code, 200)
        profile = User.objects.get(username='09121111111').profile
        self.assertFalse(profile.has_farm_location)

    def test_order_page_shows_order_steps(self):
        response = self.client.get(reverse('order', args=['wheat-harvest']))
        self.assertContains(response, 'مراحل ثبت سفارش')
        self.assertContains(response, 'خدمت و آدرس')
        self.assertContains(response, 'aria-current="step"')

    def test_guest_booking_goes_to_login(self):
        worker = User.objects.get(username='09130000001').profile.worker
        response = self.client.get(reverse('book', args=[worker.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])
