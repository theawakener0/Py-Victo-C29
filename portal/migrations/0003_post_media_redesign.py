# Generated migration for post and media redesign

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0002_add_admin_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='post',
            name='slug',
            field=models.SlugField(blank=True, max_length=220, unique=True),
        ),
        migrations.AddField(
            model_name='post',
            name='excerpt',
            field=models.TextField(blank=True, help_text='Short preview text (auto-generated if empty)', max_length=500),
        ),
        migrations.AddField(
            model_name='post',
            name='thumbnail',
            field=models.URLField(blank=True, help_text='Optional thumbnail image URL'),
        ),
        migrations.AddField(
            model_name='post',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name='post',
            name='content',
            field=models.TextField(help_text='Supports Markdown/HTML formatting'),
        ),
        migrations.CreateModel(
            name='Media',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(blank=True, max_length=200)),
                ('url', models.URLField()),
                ('media_type', models.CharField(choices=[('image', 'Image'), ('video', 'Video')], default='image', max_length=16)),
                ('thumbnail', models.URLField(blank=True, help_text='Thumbnail for videos')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('post', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='media_items', to='portal.post')),
            ],
            options={
                'verbose_name_plural': 'media',
                'ordering': ['-created_at'],
            },
        ),
    ]
