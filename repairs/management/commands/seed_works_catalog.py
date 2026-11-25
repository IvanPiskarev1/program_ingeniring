import random
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from repairs.models import FaultCategory, WorkCatalogItem


class Command(BaseCommand):
    help = 'Добавить справочник работ по категориям диагностики без изменения существующих записей.'

    @transaction.atomic
    def handle(self, *args, **options):
        rng = random.Random(20261125)
        groups = {
            'Не включается': ['Восстановление цепи запуска', 'Замена кнопки включения', 'Ремонт системной платы', 'Восстановление контактов платы'],
            'Перегрев': ['Очистка системы охлаждения', 'Замена термопасты', 'Замена вентилятора', 'Установка термопрокладок'],
            'Механическое повреждение': ['Замена корпуса', 'Замена дисплейного модуля', 'Восстановление креплений', 'Замена петель'],
            'Программный сбой': ['Восстановление операционной системы', 'Обновление прошивки', 'Удаление вредоносных программ', 'Настройка драйверов'],
            'Питание': ['Замена разъёма питания', 'Ремонт блока питания', 'Замена аккумулятора', 'Восстановление цепи зарядки'],
            'Износ деталей': ['Замена подшипников', 'Замена приводного ремня', 'Замена уплотнителя', 'Замена изношенных контактов'],
        }
        added = 0
        for category, names in groups.items():
            fault, _ = FaultCategory.objects.get_or_create(name=category)
            for name in names:
                price = Decimal(rng.randrange(6, 41) * 100)
                _, created = WorkCatalogItem.objects.get_or_create(name=name, category=fault, defaults={'price': price})
                added += int(created)
        self.stdout.write(f'Добавлено работ: {added}. Всего работ: {WorkCatalogItem.objects.count()}.')
