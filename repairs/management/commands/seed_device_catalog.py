"""Connect model-level service suggestions without rewriting devices or orders."""
import hashlib
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from repairs.models import Device, DeviceType, DeviceCatalogItem, PriceItem, WorkCatalogItem, FaultCategory
from .seed_parts_catalog import (PHONE_MODELS, PHONE_PARTS, LAPTOP_MODELS, LAPTOP_PARTS,
                                APPLIANCES, APPLIANCE_PARTS, appliance_range)


class Command(BaseCommand):
    help = 'Дополнить модели техники, детали и связанные работы без изменения заказов.'

    @transaction.atomic
    def handle(self, *args, **options):
        from django.core.management import call_command
        before = (DeviceCatalogItem.objects.count(), PriceItem.objects.count(), WorkCatalogItem.objects.count())
        call_command('seed_parts_catalog', stdout=self.stdout)
        call_command('seed_works_catalog', stdout=self.stdout)
        kinds = {}
        for code, name in [('phone', 'Телефон'), ('laptop', 'Ноутбук'), ('appliance', 'Бытовая техника')]:
            # Existing installations use «Смартфон» for phones.
            kind = DeviceType.objects.filter(name__in=['Телефон', 'Смартфон']).first() if code == 'phone' else DeviceType.objects.filter(name=name).first()
            kinds[code] = kind or DeviceType.objects.create(name=name)
        specs = {}
        for code, names, groups in [('phone', PHONE_MODELS, PHONE_PARTS), ('laptop', LAPTOP_MODELS, LAPTOP_PARTS)]:
            for full in names:
                brand, model = full.split(' ', 1)
                specs[(kinds[code].pk, brand, model)] = (code, [(g, lo, hi) for g, lo, hi in groups])
        for full, family in APPLIANCES:
            brand, model = full.split(' ', 1)
            specs[(kinds['appliance'].pk, brand, model)] = ('appliance', [(g, *appliance_range(g)) for g in APPLIANCE_PARTS[family]])
        family_words = {'washer': ['стираль', 'ww70', 'f2j3'], 'dishwasher': ['посудомо'],
                        'fridge': ['холодиль', 'nrk6191'], 'coffee': ['кофе', 'ecam'],
                        'kettle': ['чайник', 'электрочайник', 'rk-m171'], 'microwave': ['микроволн', 'mws-']}
        for d in Device.objects.select_related('kind').order_by('pk'):
            key = (d.kind_id, d.manufacturer, d.model)
            if key in specs:
                continue
            type_name = d.kind.name.casefold()
            if 'телефон' in type_name or 'смартфон' in type_name:
                code, groups = 'phone', PHONE_PARTS
            elif 'ноутбук' in type_name:
                code, groups = 'laptop', LAPTOP_PARTS
            elif 'бытов' in type_name:
                code = 'appliance'
                family = next((f for f, words in family_words.items() if any(w in d.model.casefold() for w in words)), None)
                # Ambiguous families get no invented voltage, dimensions or capacity.
                groups = [(g, *appliance_range(g)) for g in APPLIANCE_PARTS[family]] if family else [('Кнопка включения', 250, 600), ('Сетевой шнур', 300, 900)]
            else:
                # Unknown device classes need an explicit service mapping.
                # Do not invent household parts for tablets or other equipment.
                self.stdout.write(f'Неизвестный тип техники: {d.kind.name}; модель {d.manufacturer} {d.model} не дополнена автоматически.')
                continue
            specs[key] = (code, groups)
        for (kind_id, brand, model), (code, groups) in specs.items():
            entry, _ = DeviceCatalogItem.objects.get_or_create(kind_id=kind_id, manufacturer=brand, model=model, defaults={'category': code})
            for group, low, high in groups:
                name = f'{group} {brand} {model}'
                digest = hashlib.sha256(name.encode('utf-8')).hexdigest()[:16].upper()
                part = PriceItem.objects.filter(kind='part', name=name).first()
                if part is None:
                    part, _ = PriceItem.objects.get_or_create(sku=f'DC-P-{digest}', defaults={
                        'kind': 'part', 'name': name, 'price': Decimal((low + high) // 100 * 50),
                        'category': code, 'group': group, 'unit': 'шт.'})
                fault_name = ('Перегрев' if any(s in group.casefold() for s in ['кулер', 'термо', 'вентилятор']) else
                              'Питание' if any(s in group.casefold() for s in ['питани', 'аккумулятор', 'заряд', 'шнур']) else 'Износ деталей')
                fault, _ = FaultCategory.objects.get_or_create(name=fault_name)
                work, _ = WorkCatalogItem.objects.get_or_create(name=f'Замена: {group}', category=fault,
                    defaults={'price': Decimal('1500') if code != 'phone' else Decimal('1000')})
                entry.parts.add(part)
                entry.works.add(work)
                part.compatible_works.add(work)
            # Non-replacement services do not require fictional parts.
            software = WorkCatalogItem.objects.filter(category__name='Программный сбой') if code in ('phone', 'laptop') else WorkCatalogItem.objects.none()
            entry.works.add(*software)
            aliases = {
                'Замена аккумулятора': ['аккумулятор'], 'Замена дисплейного модуля': ['дисплей'],
                'Замена петель': ['петель'], 'Замена вентилятора': ['кулер', 'вентилятор'],
                'Установка термопрокладок': ['термопроклад'], 'Замена разъёма питания': ['разъём питания', 'разъём зарядки'],
                'Замена кнопки включения': ['кнопки включения', 'кнопка включения'],
                'Замена подшипников': ['подшипник'], 'Замена приводного ремня': ['ремень'],
                'Замена уплотнителя': ['уплотнител', 'манжета'], 'Замена корпуса': ['крышка', 'корпус'],
            }
            for work_name, needles in aliases.items():
                matches = [p for p in entry.parts.all() if any(n in p.group.casefold() for n in needles)]
                if matches:
                    for work in WorkCatalogItem.objects.filter(name=work_name):
                        entry.works.add(work)
                        for part in matches:
                            part.compatible_works.add(work)
            if code in ('phone', 'laptop'):
                entry.works.add(*WorkCatalogItem.objects.filter(name__in=[
                    'Восстановление цепи запуска', 'Ремонт системной платы', 'Восстановление контактов платы',
                    'Восстановление цепи зарядки', 'Очистка системы охлаждения', 'Замена термопасты', 'Восстановление креплений']))
        after = (DeviceCatalogItem.objects.count(), PriceItem.objects.count(), WorkCatalogItem.objects.count())
        self.stdout.write('Добавлено моделей: %s, деталей: %s, работ: %s.' % tuple(b-a for a, b in zip(before, after)))
        self.stdout.write('Всего моделей: %s; моделей без деталей: %s; без работ: %s.' % (
            after[0], DeviceCatalogItem.objects.filter(parts=None).count(), DeviceCatalogItem.objects.filter(works=None).count()))
