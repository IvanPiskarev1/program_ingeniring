import random
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from repairs.models import PriceItem

PHONE_MODELS = ['Apple iPhone 11', 'Apple iPhone 12', 'Apple iPhone 13', 'Apple iPhone 14',
    'Samsung Galaxy A32', 'Samsung Galaxy A52', 'Samsung Galaxy S21', 'Xiaomi Redmi Note 10',
    'Xiaomi Redmi Note 11', 'Huawei P30', 'Honor 50', 'Realme 8']
PHONE_PARTS = [('Дисплейный модуль', 2400, 14500), ('Аккумулятор', 900, 4500),
    ('Разъём зарядки', 200, 850), ('Основная камера', 1300, 6500), ('Разговорный динамик', 250, 850),
    ('Микрофон', 150, 600), ('Шлейф кнопки включения', 150, 900), ('Кнопка громкости', 200, 600),
    ('Задняя крышка', 650, 2300), ('Защитное стекло дисплея', 200, 750), ('SIM-лоток', 150, 500)]
LAPTOP_MODELS = ['Lenovo IdeaPad 3 15ITL6', 'Lenovo ThinkPad T480', 'ASUS VivoBook X515EA',
    'ASUS TUF Gaming FX506', 'HP Pavilion 15-eg', 'HP ProBook 450 G7', 'Acer Aspire A515-56',
    'Acer Nitro AN515-55', 'Dell Inspiron 3501', 'Dell Latitude 5420', 'MSI GF63 Thin 10SC', 'MSI Modern 14 B11M']
LAPTOP_PARTS = [('Матрица дисплея', 3500, 15000), ('Клавиатура', 1200, 4800), ('Аккумулятор', 2300, 6500),
    ('Блок питания', 1600, 4500), ('SSD M.2 NVMe 500 ГБ, совместимый с', 2600, 4200),
    ('Оперативная память SO-DIMM DDR4 8 ГБ, совместимая с', 1800, 3200), ('Кулер охлаждения', 800, 2700),
    ('Комплект термопрокладок для', 250, 850), ('Комплект петель экрана', 650, 2400),
    ('Разъём питания', 250, 850), ('Шлейф дисплея', 350, 900), ('Тачпад', 950, 3500)]
APPLIANCES = [
    ('Bosch WLG 20261', 'washer'), ('Samsung WW60J42E0HW', 'washer'), ('LG F2J3NS0W', 'washer'),
    ('Indesit IWSC 5105', 'washer'), ('Hotpoint-Ariston RSM 601 W', 'washer'), ('Beko WRE 6511', 'washer'),
    ('Electrolux EWS 1064', 'washer'), ('Bosch SMS 24AW01R', 'dishwasher'), ('Beko DFS 05012', 'dishwasher'),
    ('Electrolux ESF 9420', 'dishwasher'), ('Samsung RB30J3000', 'fridge'), ('LG GA-B419', 'fridge'),
    ('Indesit DF 4180', 'fridge'), ('Bosch KGN39VL', 'fridge'), ('Samsung ME83KRW', 'microwave'),
    ('LG MS2042DB', 'microwave'), ('Panasonic NN-ST251', 'microwave'), ('Bosch BGL35', 'vacuum'),
    ('Samsung SC4520', 'vacuum'), ('LG VK76A02', 'vacuum'), ('Philips HD9350', 'kettle'),
    ('Bosch TWK3A011', 'kettle'), ('DeLonghi ECAM 22.110', 'coffee'), ('Philips EP1220', 'coffee'),
    ('Bosch TIS30129', 'coffee'), ('Philips DST3041', 'iron'), ('Tefal FV1711', 'iron'),
    ('Braun MQ5200', 'blender'), ('Bosch MSM66110', 'blender'), ('Philips HR2228', 'blender')]
APPLIANCE_PARTS = {
    'washer': ['ТЭН 1900 Вт', 'Сливной насос', 'Плата управления', 'Датчик уровня воды', 'Манжета люка', 'Приводной ремень', 'Комплект подшипников', 'Двигатель', 'Датчик температуры', 'Впускной клапан', 'Фильтр сливного насоса'],
    'dishwasher': ['Проточный нагреватель', 'Сливной насос', 'Плата управления', 'Датчик уровня воды', 'Уплотнитель двери', 'Циркуляционный насос', 'Разбрызгиватель нижний', 'Замок двери', 'Датчик температуры', 'Впускной клапан', 'Сетчатый фильтр'],
    'fridge': ['Нагреватель оттайки', 'Плата управления', 'Датчик температуры', 'Уплотнитель двери', 'Вентилятор испарителя', 'Термостат', 'Пускозащитное реле', 'Компрессор', 'Термопредохранитель', 'Дренажная трубка', 'Фильтр-осушитель'],
    'microwave': ['Магнетрон', 'Высоковольтный диод', 'Высоковольтный конденсатор', 'Плата управления', 'Мотор поддона', 'Слюдяная пластина', 'Дверная защёлка', 'Микровыключатель двери', 'Сетевой предохранитель', 'Термостат', 'Лампа подсветки'],
    'vacuum': ['Двигатель', 'HEPA-фильтр', 'Входной фильтр', 'Шланг в сборе', 'Телескопическая трубка', 'Щётка пол-ковёр', 'Катушка сетевого шнура', 'Плата регулятора', 'Кнопка включения', 'Контейнер пылесборника', 'Уплотнитель контейнера'],
    'kettle': ['Нагревательный диск', 'Термостат', 'Контактная группа', 'Крышка корпуса', 'Кнопка включения', 'Фильтр от накипи', 'Подставка питания', 'Индикатор включения', 'Уплотнитель нагревателя', 'Ручка корпуса', 'Сетевой шнур'],
    'coffee': ['Термоблок', 'Помпа', 'Плата управления', 'Датчик расхода воды', 'Уплотнитель заварочного блока', 'Клапан подачи воды', 'Двигатель кофемолки', 'Жернова кофемолки', 'Датчик температуры', 'Трубка подачи воды', 'Фильтр воды'],
    'iron': ['Подошва с нагревателем', 'Термостат', 'Термопредохранитель', 'Сетевой шнур', 'Кнопка подачи пара', 'Клапан подачи воды', 'Уплотнитель резервуара', 'Резервуар воды', 'Ручка корпуса', 'Индикатор нагрева', 'Регулятор температуры'],
    'blender': ['Двигатель', 'Ножевой блок', 'Муфта привода', 'Редуктор', 'Плата управления', 'Кнопка включения', 'Уплотнитель чаши', 'Чаша измельчителя', 'Крышка измельчителя', 'Венчик в сборе', 'Сетевой шнур'],
}


def appliance_range(name):
    if 'Плата' in name: return 2500, 12000
    if 'Компрессор' in name: return 5500, 11500
    if any(s in name for s in ('Двигатель', 'насос', 'Помпа', 'Термоблок', 'Магнетрон')): return 1500, 6500
    if any(s in name for s in ('ТЭН', 'нагревател', 'Нагревател')): return 900, 3800
    return 250, 2200


class Command(BaseCommand):
    help = 'Добавить каталог совместимых деталей без изменения существующих позиций.'

    @transaction.atomic
    def handle(self, *args, **options):
        rng = random.Random(20261125)
        rows = []
        for category, models, parts in [('phone', PHONE_MODELS, PHONE_PARTS), ('laptop', LAPTOP_MODELS, LAPTOP_PARTS)]:
            for model in models:
                for group, low, high in parts:
                    # Higher-end phone modules cost more, without random outliers.
                    if category == 'phone' and group == 'Дисплейный модуль':
                        low, high = (6500, 14500) if model.startswith('Apple') else (2400, 7500)
                    rows.append((category, group, f'{group} {model}', low, high))
        for model, family in APPLIANCES:
            for group in APPLIANCE_PARTS[family]:
                low, high = appliance_range(group)
                rows.append(('appliance', group, f'{group} {model}', low, high))
        added = 0
        for index, (category, group, name, low, high) in enumerate(rows, 1):
            price = Decimal(rng.randrange(low // 50, high // 50 + 1) * 50)
            sku = f'AS-P-{index:05d}'
            # Preserve a pre-existing name/price, but still add this SKU as a
            # distinct compatible catalogue position. Repeats use the same SKU.
            if not PriceItem.objects.filter(sku=sku).exists() and PriceItem.objects.filter(name=name).exists():
                name = f'{name} ({sku})'
            _, created = PriceItem.objects.get_or_create(sku=sku, defaults={
                'kind': 'part', 'name': name, 'price': price, 'category': category,
                'group': group, 'unit': 'шт.', 'is_active': True})
            added += int(created)
        self.stdout.write(self.style.SUCCESS(f'Добавлено деталей: {added}. Всего деталей: {PriceItem.objects.filter(kind="part").count()}.'))
