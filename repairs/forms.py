import uuid
from django import forms
from django.contrib.auth.models import User
from .models import Client, Device, DeviceType, Diagnosis, Payment, QualityCheck, RepairOrder, RepairWork, UsedPart


class IntakeForm(forms.Form):
    request_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    existing_client = forms.ModelChoiceField(label='Существующий клиент', queryset=Client.objects.all(), required=False, empty_label='Новый клиент — заполнить ниже')
    kind = forms.ChoiceField(label='Тип клиента', choices=Client._meta.get_field('kind').choices)
    client_name = forms.CharField(label='Имя / организация', max_length=160, required=False)
    contact = forms.CharField(label='Контактное лицо', max_length=160, required=False)
    phone = forms.CharField(label='Телефон', max_length=30, required=False)
    email = forms.EmailField(label='E-mail', required=False)
    existing_device = forms.ModelChoiceField(label='Ранее принятое изделие', queryset=Device.objects.all(), required=False, empty_label='Новое изделие — заполнить ниже')
    device_type = forms.ModelChoiceField(label='Тип техники', queryset=DeviceType.objects.all(), required=False)
    manufacturer = forms.CharField(label='Производитель', max_length=100, required=False)
    device_model = forms.CharField(label='Модель', max_length=120, required=False)
    serial = forms.CharField(label='Серийный номер', max_length=120, required=False)
    problem = forms.CharField(label='Заявленная неисправность', widget=forms.Textarea(attrs={'rows': 3}))
    accessories = forms.CharField(label='Комплектность', required=False, widget=forms.Textarea(attrs={'rows': 2}))
    appearance = forms.CharField(label='Внешний вид при приёме', required=False, widget=forms.Textarea(attrs={'rows': 2}))
    def clean(self):
        data = super().clean()
        if not data.get('existing_client'):
            for name in ('client_name', 'phone'):
                if not data.get(name):
                    self.add_error(name, 'Заполните поле или выберите существующего клиента.')
            if data.get('phone'):
                try:
                    Client._meta.get_field('phone').run_validators(data['phone'])
                except forms.ValidationError as exc:
                    self.add_error('phone', exc)
        if not data.get('existing_device'):
            for name in ('device_type', 'manufacturer', 'device_model'):
                if not data.get(name):
                    self.add_error(name, 'Заполните поле или выберите ранее принятое изделие.')
        return data


class AssignForm(forms.Form):
    master = forms.ModelChoiceField(label='Мастер', queryset=User.objects.filter(is_active=True, groups__name='Мастер').distinct())


class DiagnosisForm(forms.ModelForm):
    estimate = forms.DecimalField(label='Предварительная стоимость, ₽', min_value=0, max_digits=12, decimal_places=2)
    due_date = forms.DateField(label='Плановая дата', widget=forms.DateInput(attrs={'type': 'date'}))
    class Meta:
        model = Diagnosis
        fields = ['result', 'category', 'required_parts']
        widgets = {'result': forms.Textarea(attrs={'rows': 3}), 'required_parts': forms.Textarea(attrs={'rows': 2})}


class WorkForm(forms.ModelForm):
    class Meta:
        model = RepairWork
        fields = ['description', 'minutes', 'cost']


class PartForm(forms.ModelForm):
    class Meta:
        model = UsedPart
        fields = ['name', 'quantity', 'price']


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
        labels = {'amount': 'Сумма учебной оплаты, ₽', 'method': 'Способ расчёта'}


class IssueForm(forms.Form):
    issue_method = forms.CharField(label='Способ выдачи', max_length=160, initial='Лично клиенту в сервисном центре')
    free_reason = forms.CharField(label='Причина бесплатного ремонта (если сумма 0)', max_length=240, required=False)


class EmptyForm(forms.Form):
    pass


class ReportForm(forms.Form):
    start = forms.DateField(label='С', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    end = forms.DateField(label='По', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    def clean(self):
        data = super().clean()
        if data.get('start') and data.get('end') and data['start'] > data['end']:
            raise forms.ValidationError('Начало периода не может быть позже окончания.')
        return data
