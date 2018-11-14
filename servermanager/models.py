from django.db import models


# Create your models here.
class commands(models.Model):
    title = models.CharField('Название команды', max_length=300)
    command = models.CharField('Приказы', max_length=2000)
    describe = models.CharField('Описание команды', max_length=300)
    created_time = models.DateTimeField('Время создания', auto_now_add=True)
    last_mod_time = models.DateTimeField('Время изменения', auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = 'Приказы'
        verbose_name_plural = verbose_name


class EmailSendLog(models.Model):
    emailto = models.CharField('Получатели', max_length=300)
    title = models.CharField('Заголовок сообщения', max_length=2000)
    content = models.TextField('Содержание сообщения')
    send_result = models.BooleanField('Результаты', default=False)
    created_time = models.DateTimeField('Время создания', auto_now_add=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = 'Журнал отправки почты'
        verbose_name_plural = verbose_name
        ordering = ['-created_time']
