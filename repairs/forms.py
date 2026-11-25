import uuid
from django import forms
from django.contrib.auth.models import User
from .models import Client, Device, DeviceCatalogItem, DeviceType, Diagnosis, Payment, PriceItem, QualityCheck, RepairOrder, RepairWork, UsedPart, WorkCatalogItem


class IntakeForm(forms.Form):
    request_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    existing_client = forms.ModelChoiceField(label='Существующий клиент', queryset=Client.objects.all(), required=False, empty_label='Новый клиент - заполнить ниже')
    kind = forms.ChoiceField(label='Тип клиента', choices=Client._meta.get_field('kind').choices)
    client_name = forms.CharField(label='Имя / организация', max_length=160, required=False)
    contact = forms.CharField(label='Контактное лицо', max_length=160, required=False)
    phone = forms.CharField(label='Телефон', max_length=30, required=False)
    email = forms.EmailField(label='E-mail', required=False)
    email_notifications = forms.BooleanField(label='Клиент согласен получать уведомления о статусе по почте (для нового клиента)', required=False)
    existing_device = forms.ModelChoiceField(label='Ранее принятое изделие', help_text='Только изделия выбранного клиента. Для нового устройства используйте справочник моделей ниже.', queryset=Device.objects.all(), required=False, empty_label='Новое изделие - заполнить ниже')
    catalog_model = forms.ModelChoiceField(label='Модель из справочника (новое изделие)', queryset=DeviceCatalogItem.objects.all(), required=False, empty_label='Выберите модель или заполните вручную')
    device_type = forms.ModelChoiceField(label='Тип техники', queryset=DeviceType.objects.all(), required=False)
    manufacturer = forms.CharField(label='Производитель', max_length=100, required=False)
    device_model = forms.CharField(label='Модель', max_length=120, required=False)
    serial = forms.CharField(label='Серийный номер', max_length=120, required=False)
    problem = forms.CharField(label='Заявленная неисправность', widget=forms.Textarea(attrs={'rows': 3}))
    accessories = forms.CharField(label='Комплектность', required=False, widget=forms.Textarea(attrs={'rows': 2}))
    appearance = forms.CharField(label='Внешний вид при приёме', required=False, widget=forms.Textarea(attrs={'rows': 2}))
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        client_id = self.data.get('existing_client') if self.is_bound else self.initial.get('existing_client')
        self.fields['existing_device'].queryset = Device.objects.filter(orders__client_id=client_id).distinct() if str(client_id or '').isdigit() else Device.objects.none()
        self.fields['existing_device'].error_messages['invalid_choice'] = 'Изделие не принадлежит выбранному клиенту.'
        self.fields['email_notifications'].label = 'Согласие на уведомления по почте'

    def clean(self):
        data = super().clean()
        selected = data.get('existing_client')
        if selected:
            for field, attr in [('client_name', 'name'), ('kind', 'kind'), ('contact', 'contact'), ('phone', 'phone'), ('email', 'email')]:
                if field not in self.data:
                    data[field] = getattr(selected, attr)
        if not selected:
            if data.get('email_notifications') and not data.get('email'):
                self.add_error('email', 'Укажите почту для уведомлений.')
            for name in ('client_name', 'phone'):
                if not data.get(name):
                    self.add_error(name, 'Заполните поле или выберите существующего клиента.')
            if data.get('phone'):
                try:
                    Client._meta.get_field('phone').run_validators(data['phone'])
                except forms.ValidationError as exc:
                    self.add_error('phone', exc)
        if data.get('phone'):
            from .intake_data import phone_key
            matches = [c for c in Client.objects.exclude(pk=selected.pk if selected else None) if phone_key(c.phone) == phone_key(data['phone'])]
            if matches:
                self.add_error('phone', 'Клиент с таким телефоном уже существует. Выберите существующего клиента: ' + ', '.join(c.name for c in matches[:3]))
        if selected:
            for name in ('client_name', 'phone'):
                if not data.get(name):
                    self.add_error(name, 'Заполните поле.')
            try:
                Client._meta.get_field('phone').run_validators(data.get('phone', ''))
            except forms.ValidationError as exc:
                self.add_error('phone', exc)
            if data.get('email_notifications') and not data.get('email'):
                self.add_error('email', 'Укажите почту для уведомлений.')
        if data.get('existing_device') and not selected:
            self.add_error('existing_device', 'Сначала выберите клиента.')
        catalog = data.get('catalog_model')
        if catalog and data.get('existing_device'):
            self.add_error('catalog_model', 'Выберите ранее принятое изделие или модель нового устройства, не оба варианта одновременно.')
        if catalog and not data.get('existing_device'):
            data.update(device_type=catalog.kind, manufacturer=catalog.manufacturer, device_model=catalog.model)
        if not data.get('existing_device'):
            for name in ('device_type', 'manufacturer', 'device_model'):
                if not data.get(name):
                    self.add_error(name, 'Заполните поле или выберите ранее принятое изделие.')
        return data


class AssignForm(forms.Form):
    master = forms.ModelChoiceField(label='Мастер', queryset=User.objects.filter(is_active=True, groups__name='Мастер').distinct())


class DiagnosisForm(forms.ModelForm):
    estimate = forms.DecimalField(label='Предварительная стоимость ремонта, ₽ (без диагностики)', min_value=0, max_digits=12, decimal_places=2)
    diagnosis_price = forms.DecimalField(label='Стоимость диагностики, ₽', min_value=0, max_digits=12, decimal_places=2, initial=500, required=False)
    due_date = forms.DateField(label='Плановая дата', widget=forms.DateInput(attrs={'type': 'date'}))
    class Meta:
        model = Diagnosis
        fields = ['result', 'category']
        widgets = {'result': forms.Textarea(attrs={'rows': 3}), 'required_parts': forms.Textarea(attrs={'rows': 2})}


class PriceChoiceForm(forms.Form):
    """Select an item from the price list; leave blank to enter a custom row."""
    price_item = forms.ModelChoiceField(label='Из прайс-листа', queryset=PriceItem.objects.filter(is_active=True), required=False, empty_label='Ввести вручную')


class WorkForm(PriceChoiceForm, forms.ModelForm):
    price_item = forms.ModelChoiceField(label='Из прайс-листа', queryset=WorkCatalogItem.objects.filter(is_active=True), required=False, empty_label='Ввести вручную')
    description = forms.CharField(label='Выполненная работа', max_length=240, required=False)
    cost = forms.DecimalField(label='Стоимость работы, ₽', min_value=0, max_digits=12, decimal_places=2, required=False)

    class Meta:
        model = RepairWork
        fields = ['description', 'minutes', 'cost']

    def clean(self):
        data = super().clean()
        item = data.get('price_item')
        if item:
            data['description'] = item.name
            data['cost'] = item.price
        else:
            for field in ('description', 'cost'):
                if data.get(field) in (None, ''):
                    self.add_error(field, 'Заполните поле или выберите работу из прайс-листа.')
        return data


class PartForm(PriceChoiceForm, forms.ModelForm):
    price_item = forms.ModelChoiceField(label='Из прайс-листа', queryset=PriceItem.objects.filter(is_active=True, kind='part'), required=False, empty_label='Ввести вручную')
    name = forms.CharField(label='Деталь', max_length=180, required=False)
    price = forms.DecimalField(label='Цена за единицу, ₽', max_digits=12, decimal_places=2, min_value=0, required=False)

    class Meta:
        model = UsedPart
        fields = ['name', 'quantity', 'price']

    def clean(self):
        data = super().clean()
        item = data.get('price_item')
        if item:
            data['name'] = item.name
            data['price'] = item.price
        else:
            for field in ('name', 'price'):
                if data.get(field) in (None, ''):
                    self.add_error(field, 'Заполните поле или выберите деталь из прайс-листа.')
        return data


class QualityForm(forms.ModelForm):
    passed = forms.TypedChoiceField(label='Результат', choices=[('yes', 'Допустить к выдаче'), ('no', 'Вернуть в ремонт')], coerce=lambda v: v == 'yes')
    class Meta:
        model = QualityCheck
        fields = ['passed', 'comment']
        widgets = {'comment': forms.Textarea(attrs={'rows': 3})}


class PaymentForm(forms.ModelForm):
    request_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    class Meta:
        model = Payment
        fields = ['amount', 'method']
        labels = {'amount': 'Сумма оплаты, ₽', 'method': 'Способ расчёта'}


class EstimateApprovalForm(forms.Form):
    amount = forms.DecimalField(label='Согласованная стоимость, ₽', min_value=0, max_digits=12, decimal_places=2)
    note = forms.CharField(label='Комментарий к согласованию', max_length=240, required=False, widget=forms.Textarea(attrs={'rows': 2}))


class IssueForm(forms.Form):
    issue_method = forms.CharField(label='Способ выдачи', max_length=160, initial='Лично клиенту в сервисном центре')
    free_reason = forms.CharField(label='Причина бесплатного ремонта (если сумма 0)', max_length=240, required=False)


class EmptyForm(forms.Form):
    pass


class ReportForm(forms.Form):
    start = forms.DateField(label='С', required=False, widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}))
    end = forms.DateField(label='По', required=False, widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}))
    def clean(self):
        data = super().clean()
        if data.get('start') and data.get('end') and data['start'] > data['end']:
            raise forms.ValidationError('Начало периода не может быть позже окончания.')
        return data
