from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('users', '0010_user_acesso_especial_cpf_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='acesso_especial_cpf',
            field=models.BooleanField(default=True, help_text='Usuário pode fazer login via link especial usando apenas CPF', verbose_name='Acesso Especial via CPF'),
        ),
    ]
