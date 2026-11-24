# Generated to localize QualityCheck.comment and StatusHistory.comment labels
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('repairs', '0004_priceitem_diagnosis_price')]

    operations = [
        migrations.AlterField(model_name='qualitycheck', name='comment', field=models.TextField(verbose_name='Комментарий')),
        migrations.AlterField(model_name='statushistory', name='comment', field=models.TextField(blank=True, verbose_name='Комментарий')),
    ]
