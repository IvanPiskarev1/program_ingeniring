from django import forms
from django.forms import formset_factory, BaseFormSet
from .models import PriceItem, WorkCatalogItem


class DiagnosticItemForm(forms.Form):
    kind = forms.ChoiceField(label='Тип', choices=[('part', 'Деталь'), ('work', 'Работа')])
    catalog_id = forms.IntegerField(required=False, min_value=1, widget=forms.HiddenInput)
    name = forms.CharField(label='Название или артикул', max_length=180, required=False)
    quantity = forms.IntegerField(label='Количество', min_value=1, max_value=10000, initial=1, required=False)
    price = forms.DecimalField(label='Цена, ₽', min_value=0, max_digits=12, decimal_places=2, required=False)

    def clean(self):
        data = super().clean()
        if not data.get('name') and not data.get('catalog_id') and data.get('price') is None:
            data['empty'] = True
            return data
        if data.get('catalog_id') and data.get('kind'):
            model = PriceItem if data['kind'] == 'part' else WorkCatalogItem
            query = model.objects.filter(pk=data['catalog_id'], is_active=True)
            if data['kind'] == 'part':
                query = query.filter(kind='part')
            item = query.first()
            if not item:
                raise forms.ValidationError('Позиция справочника недоступна. Выберите другую или введите вручную.')
            data['name'], data['price'] = item.name, item.price
        else:
            if len(data.get('name', '').strip()) < 2:
                self.add_error('name', 'Введите осмысленное название (не менее 2 символов).')
            if data.get('price') is None:
                self.add_error('price', 'Укажите цену.')
        if data.get('quantity') is None:
            self.add_error('quantity', 'Укажите положительное целое количество.')
        if data.get('price') is not None and data.get('quantity') and data['price'] * data['quantity'] > 9999999999:
            self.add_error('price', 'Стоимость позиции слишком велика.')
        return data


class ItemFormSet(BaseFormSet):
    def clean(self):
        super().clean()
        # Empty rows remain ignorable even when default type/quantity changed.
        for form in self.forms:
            if form.cleaned_data.get('empty'):
                form._errors.clear()


DiagnosticItemFormSet = formset_factory(DiagnosticItemForm, formset=ItemFormSet, extra=1, max_num=100, validate_max=True, absolute_max=100)


def validate_items(rows):
    """Re-read catalog values inside the order transaction, never trust POST snapshots."""
    from django.core.exceptions import ValidationError
    if len(rows) > 100:
        raise ValidationError('Не более 100 позиций за один раз.')
    result = []
    for row in rows:
        form = DiagnosticItemForm(row)
        if not form.is_valid():
            raise ValidationError('Проверьте позиции диагностики: ' + '; '.join(str(e) for errors in form.errors.values() for e in errors))
        if not form.cleaned_data.get('empty'):
            result.append(form.cleaned_data)
    return result
