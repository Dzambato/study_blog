import logging
from abc import ABCMeta, abstractmethod, abstractproperty

from django.db import models
from django.urls import reverse
from django.conf import settings
from uuslug import slugify
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.contrib.sites.models import Site
from DjangoBlog.utils import cache_decorator, cache
from django.utils.functional import cached_property
from django.utils.timezone import now

logger = logging.getLogger(__name__)

LINK_SHOW_TYPE = (
    ('i', 'Домашняя'),
    ('l', 'страница списка'),
    ('p', 'страница статьи'),
    ('a', 'все станции'),
)


class BaseModel(models.Model):
    id = models.AutoField(primary_key=True)
    created_time = models.DateTimeField("Время создания", default=now)
    last_mod_time = models.DateTimeField('Время изменения', default=now)

    def save(self, *args, **kwargs):

        if not isinstance(self, Article) and 'slug' in self.__dict__:
            if getattr(self, 'slug') == 'no-slug' or not self.id:
                slug = getattr(self, 'title') if 'title' in self.__dict__ else getattr(self, 'name')
                setattr(self, 'slug', slugify(slug))
        super().save(*args, **kwargs)
        # is_update_views = 'update_fields' in kwargs and len(kwargs['update_fields']) == 1 and kwargs['update_fields'][
        #     0] == 'views'
        # from DjangoBlog.blog_signals import article_save_signal
        # article_save_signal.send(sender=self.__class__, is_update_views=is_update_views, id=self.id)

    def get_full_url(self):
        site = Site.objects.get_current().domain
        url = "https://{site}{path}".format(site=site, path=self.get_absolute_url())
        return url

    class Meta:
        abstract = True

    @abstractmethod
    def get_absolute_url(self):
        pass


class Article(BaseModel):
    """Статья"""
    STATUS_CHOICES = (
        ('d','черновик'),
        ('p', 'опубликовано'),
    )
    COMMENT_STATUS = (
        ('o', 'Open'),
        ('c', 'off'),
    )
    TYPE = (
        ('a','статья'),
        ('p', 'страница'),
    )
    title = models.CharField('Название', max_length=200, unique=True)
    body = models.TextField('Тело')
    pub_time = models.DateTimeField('Время публикации', blank=True, null=True)
    status = models.CharField('Статус статьи', max_length=1, choices=STATUS_CHOICES, default='p')
    comment_status = models.CharField('Статус комментариев', max_length=1, choices=COMMENT_STATUS, default='o')
    type = models.CharField('Тип', max_length=1, choices=TYPE, default='a')
    views = models.PositiveIntegerField('Количество просмотров', default=0)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Автор', on_delete=models.CASCADE)
    article_order = models.IntegerField('Сортировка, чем больше число, тем больше вперед', blank=False, null=False, default=0)
    category = models.ForeignKey('Category', verbose_name='Классификация', on_delete=models.CASCADE, blank=False, null=False)
    tags = models.ManyToManyField('Tag', verbose_name='Коллекция тегов', blank=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-article_order', '-pub_time']
        verbose_name = "Статьи"
        verbose_name_plural = verbose_name
        get_latest_by = 'id'

    def get_absolute_url(self):
        return reverse('blog:detailbyid', kwargs={
            'article_id': self.id,
            'year': self.created_time.year,
            'month': self.created_time.month,
            'day': self.created_time.day
        })

    @cache_decorator(60 * 60 * 10)
    def get_category_tree(self):
        tree = self.category.get_category_tree()
        names = list(map(lambda c: (c.name, c.get_absolute_url()), tree))

        return names

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def viewed(self):
        self.views += 1
        self.save(update_fields=['views'])

    def comment_list(self):
        cache_key = 'article_comments_{id}'.format(id=self.id)
        value = cache.get(cache_key)
        if value:
            logger.info('get article comments:{id}'.format(id=self.id))
            return value
        else:
            comments = self.comment_set.filter(is_enable=True)
            cache.set(cache_key, comments)
            logger.info('set article comments:{id}'.format(id=self.id))
            return comments

    def get_admin_url(self):
        info = (self._meta.app_label, self._meta.model_name)
        return reverse('admin:%s_%s_change' % info, args=(self.pk,))

    @cached_property
    def next_article(self):
        # 下一篇
        return Article.objects.filter(id__gt=self.id, status='p').order_by('id').first()

    @cached_property
    def prev_article(self):
        # 前一篇
        return Article.objects.filter(id__lt=self.id, status='p').first()


class Category(BaseModel):
    """文章分类"""
    name = models.CharField('Название категории', max_length=30, unique=True)
    parent_category = models.ForeignKey('self', verbose_name="Родительская классификация", blank=True, null=True, on_delete=models.CASCADE)
    slug = models.SlugField(default='no-slug', max_length=60, blank=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Классификация"
        verbose_name_plural = verbose_name

    def get_absolute_url(self):
        return reverse('blog:category_detail', kwargs={'category_name': self.slug})

    def __str__(self):
        return self.name

    @cache_decorator(60 * 60 * 10)
    def get_category_tree(self):
        """
        递归获得分类目录的父级
        :return: 
        """
        categorys = []

        def parse(category):
            categorys.append(category)
            if category.parent_category:
                parse(category.parent_category)

        parse(self)
        return categorys

    @cache_decorator(60 * 60 * 10)
    def get_sub_categorys(self):
        """
        获得当前分类目录所有子集
        :return: 
        """
        categorys = []
        all_categorys = Category.objects.all()

        def parse(category):
            if category not in categorys:
                categorys.append(category)
            childs = all_categorys.filter(parent_category=category)
            for child in childs:
                if category not in categorys:
                    categorys.append(child)
                parse(child)

        parse(self)
        return categorys


class Tag(BaseModel):
    """文章标签"""
    name = models.CharField('Имя тега', max_length=30, unique=True)
    slug = models.SlugField(default='no-slug', max_length=60, blank=True)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('blog:tag_detail', kwargs={'tag_name': self.slug})

    @cache_decorator(60 * 60 * 10)
    def get_article_count(self):
        return Article.objects.filter(tags__name=self.name).distinct().count()

    class Meta:
        ordering = ['name']
        verbose_name = "Ярлык"
        verbose_name_plural = verbose_name


class Links(models.Model):
    """友情链接"""

    name = models.CharField('имя ссылки', max_length=30, unique=True)
    link = models.URLField('адрес ссылки')
    sequence = models.IntegerField('Сортировка', unique=True)
    is_enable = models.BooleanField('Отображается ли', default=True, blank=False, null=False)
    show_type = models.CharField('тип дисплея', max_length=1, choices=LINK_SHOW_TYPE, default='i')
    created_time = models.DateTimeField('Время создания', default=now)
    last_mod_time = models.DateTimeField('Время изменения', default=now)

    class Meta:
        ordering = ['sequence']
        verbose_name = 'Ссылки'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class SideBar(models.Model):
    """侧边栏,可以展示一些html内容"""
    name = models.CharField('Имя', max_length=100)
    content = models.TextField("Содержание")
    sequence = models.IntegerField('Сортировка', unique=True)
    is_enable = models.BooleanField('Включен ли', default=True)
    created_time = models.DateTimeField('Время создания', default=now)
    last_mod_time = models.DateTimeField('Время модификации', default=now)

    class Meta:
        ordering = ['sequence']
        verbose_name = 'Боковая панель'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class BlogSettings(models.Model):
    '''站点设置 '''
    sitename = models.CharField("Название сайта", max_length=200, null=False, blank=False, default='')
    site_description = models.TextField("Описание сайта", max_length=1000, null=False, blank=False, default='')
    site_seo_description = models.TextField("SEO описание сайта", max_length=1000, null=False, blank=False, default='')
    site_keywords = models.TextField("Ключевые слова сайта", max_length=1000, null=False, blank=False, default='')
    article_sub_length = models.IntegerField("Длина тезисов статей", default=300)
    sidebar_article_count = models.IntegerField("Количество статей на боковой панели", default=10)
    sidebar_comment_count = models.IntegerField("Количество комментариев на боковой панели", default=5)
    show_google_adsense = models.BooleanField('Показывать ли объявления Google', default=False)
    google_adsense_codes = models.TextField('Содержание рекламы', max_length=2000, null=True, blank=True, default='')
    open_site_comment = models.BooleanField('Включить функцию обзора веб-сайта', default=True)
    beiancode = models.CharField('Номер записи', max_length=2000, null=True, blank=True, default='')
    analyticscode = models.TextField("Код статистики сайта", max_length=1000, null=False, blank=False, default='')
    show_gongan_code = models.BooleanField('Показывает ли номер записи общественной безопасности', default=False, null=False)
    gongan_beiancode = models.TextField('Номер записи общественной безопасности', max_length=2000, null=True, blank=True, default='')
    resource_path = models.CharField("Статический адрес сохранения файла", max_length=300, null=False, default='/var/www/resource/')

    class Meta:
        verbose_name = 'Конфигурация сайта'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.sitename

    def clean(self):
        if BlogSettings.objects.exclude(id=self.id).count():
            raise ValidationError(_('Может быть только одна конфигурация'))

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from DjangoBlog.utils import cache
        cache.clear()
