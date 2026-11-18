import secrets
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone


def access_token():
    return secrets.token_urlsafe(32)


class DeviceType(models.Model):
    name = models.CharField('Название', max_length=100, unique=True)
    class Meta:
        verbose_name = 'тип изделия'
        verbose_name_plural = 'Типы изделий'
    def __str__(self):
        return self.name


class FaultCategory(models.Model):
    name = models.CharField('Название', max_length=100, unique=True)
    class Meta:
        verbose_name = 'категория неисправности'
        verbose_name_plural = 'Категории неисправностей'
    def __str__(self):
        return self.name


class NotificationTemplate(models.Model):
    name = models.CharField('Название', max_length=100, unique=True)
    text = models.TextField('Текст', help_text='Доступны {number}, {status}. Без персональных данных.')
    class Meta:
        verbose_name = 'шаблон уведомления'
        verbose_name_plural = 'Шаблоны уведомлений'
    def __str__(self):
        return self.name


class Client(models.Model):
    kind = models.CharField('Тип клиента', max_length=10, choices=[('person', 'Частный'), ('company', 'Организация')], default='person')
    name = models.CharField('Имя / название', max_length=160)
    contact = models.CharField('Контактное лицо', max_length=160, blank=True)
    phone = models.CharField('Телефон', max_length=30, validators=[RegexValidator(r'^\+?[\d\s()\-]{7,30}$', 'Введите телефон: от 7 цифр, допустимы +, пробелы и скобки.')])
    email = models.EmailField('E-mail', blank=True)
    email_notifications = models.BooleanField('Согласие на уведомления по почте', default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        verbose_name = 'клиент'
        verbose_name_plural = 'Клиенты'
        ordering = ['name']
    def __str__(self):
        return f'{self.name} · {self.phone}'


class Device(models.Model):
    kind = models.ForeignKey(DeviceType, on_delete=models.PROTECT, verbose_name='Тип устройства')
    manufacturer = models.CharField('Производитель', max_length=100)
    model = models.CharField('Модель', max_length=120)
    serial = models.CharField('Серийный номер', max_length=120, blank=True, db_index=True)
    class Meta:
        verbose_name = 'изделие'
        verbose_name_plural = 'Изделия'
    def __str__(self):
        return f'{self.manufacturer} {self.model} · ID {self.pk}'


class IntakeRequest(models.Model):
    """Transactional reservation serializes duplicate intake submissions."""
    key = models.UUIDField(primary_key=True)
    created_at = models.DateTimeField(default=timezone.now)


class RepairOrder(models.Model):
    class Status(models.TextChoices):
        RECEIVED = 'received', 'Принято'
        DIAGNOSIS = 'diagnosis', 'Диагностика'
        REPAIR = 'repair', 'Ремонт'
        QUALITY = 'quality', 'Контроль качества'
        READY = 'ready', 'Готово к выдаче'
        ISSUED = 'issued', 'Выдано'
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='orders', verbose_name='Клиент')
    device = models.ForeignKey(Device, on_delete=models.PROTECT, related_name='orders', verbose_name='Изделие')
    master = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='assigned_orders')
    problem = models.TextField('Заявленная неисправность')
    accessories = models.TextField('Комплектность', blank=True)
    appearance = models.TextField('Внешний вид', blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RECEIVED, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    due_date = models.DateField('Плановая дата', null=True, blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    issue_method = models.CharField(max_length=160, blank=True)
    estimate = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    free_reason = models.CharField(max_length=240, blank=True)
    token = models.CharField(max_length=64, unique=True, default=access_token, editable=False)
    request_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    version = models.PositiveIntegerField(default=0)
    class Meta:
        ordering = ['-created_at', '-pk']
        verbose_name = 'заказ'
        verbose_name_plural = 'Заказы'
        constraints = [models.CheckConstraint(condition=models.Q(estimate__gte=0) | models.Q(estimate__isnull=True), name='order_estimate_nonnegative')]
    @property
    def number(self):
        return f'АС-{self.pk:06d}'
    @property
    def final_total(self):
        return sum((w.cost for w in self.works.all()), Decimal('0.00')) + sum((p.quantity * p.price for p in self.parts.all()), Decimal('0.00'))
    @property
    def paid_total(self):
        return sum((p.amount for p in self.payments.all()), Decimal('0.00'))
    @property
    def balance(self):
        return self.final_total - self.paid_total
    @property
    def overdue(self):
        return bool(self.due_date and self.due_date < timezone.localdate() and self.status != self.Status.ISSUED)
    def __str__(self):
        return self.number


class Diagnosis(models.Model):
    order = models.OneToOneField(RepairOrder, on_delete=models.PROTECT, related_name='diagnosis')
    result = models.TextField('Результаты диагностики')
    category = models.ForeignKey(FaultCategory, on_delete=models.PROTECT, verbose_name='Категория')
    required_parts = models.TextField('Необходимые детали', blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)


class RepairWork(models.Model):
    order = models.ForeignKey(RepairOrder, on_delete=models.PROTECT, related_name='works')
    description = models.CharField('Выполненная работа', max_length=240)
    minutes = models.PositiveIntegerField('Трудозатраты, мин', default=0)
    cost = models.DecimalField('Стоимость работы, ₽', max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)
    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(cost__gte=0), name='work_cost_nonnegative')]


class UsedPart(models.Model):
    order = models.ForeignKey(RepairOrder, on_delete=models.PROTECT, related_name='parts')
    name = models.CharField('Деталь', max_length=180)
    quantity = models.PositiveIntegerField('Количество', validators=[MinValueValidator(1)])
    price = models.DecimalField('Цена за единицу, ₽', max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gte=1, price__gte=0), name='part_valid_values')]


class QualityCheck(models.Model):
    order = models.ForeignKey(RepairOrder, on_delete=models.PROTECT, related_name='checks')
    passed = models.BooleanField()
    comment = models.TextField()
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)


class StatusHistory(models.Model):
    order = models.ForeignKey(RepairOrder, on_delete=models.PROTECT, related_name='history')
    old_status = models.CharField(max_length=12, choices=RepairOrder.Status.choices, blank=True)
    new_status = models.CharField(max_length=12, choices=RepairOrder.Status.choices)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    class Meta:
        ordering = ['created_at', 'pk']


class Notification(models.Model):
    event = models.OneToOneField(StatusHistory, on_delete=models.PROTECT, related_name='notification')
    channel = models.CharField(max_length=12, default='journal')
    text = models.TextField()
    recipient = models.EmailField(blank=True)
    state = models.CharField(max_length=12, default='pending', choices=[('pending', 'Ожидает отправки'), ('sending', 'Передаётся серверу'), ('sent', 'Передано почтовому серверу'), ('skipped', 'Не отправляется'), ('unknown', 'Результат неизвестен'), ('test', 'Старая запись'), ('error', 'Ошибка отправки')])
    sent_at = models.DateTimeField(null=True, blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)


class Payment(models.Model):
    order = models.ForeignKey(RepairOrder, on_delete=models.PROTECT, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    method = models.CharField(max_length=12, choices=[('cash', 'Наличные'), ('card', 'Карта')])
    request_key = models.UUIDField(unique=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    is_demo = models.BooleanField(default=True, editable=False)
    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name='payment_positive')]


class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    order = models.ForeignKey(RepairOrder, on_delete=models.PROTECT, null=True, blank=True)
    action = models.CharField(max_length=240)
    created_at = models.DateTimeField(default=timezone.now)
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'событие аудита'
        verbose_name_plural = 'Аудит'
