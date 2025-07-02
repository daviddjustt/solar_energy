import os
from os.path import join
from distutils.util import strtobool
import dj_database_url
from configurations import Configuration
from datetime import timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class Common(Configuration):
    INSTALLED_APPS = (
        'django.contrib.admin',
        'django.contrib.auth',
        'django.contrib.contenttypes',
        'django.contrib.sessions',
        'django.contrib.messages',
        'django.contrib.staticfiles',

        # Third party apps
        'rest_framework', # utilities for rest apis
        'rest_framework.authtoken', # token authentication
        'django_filters', # for filtering rest endpoints
        'drf_spectacular',
        'corsheaders',
        'djoser',
        'rest_framework_simplejwt.token_blacklist',
        'import_export',
        
        # Your apps
        'solar.users',
        'solar.documents',
    )
    # https://docs.djangoproject.com/en/2.0/topics/http/middleware/
    MIDDLEWARE = (
        'django.middleware.security.SecurityMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        'corsheaders.middleware.CorsMiddleware',
        'django.middleware.common.CommonMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
        'django.contrib.messages.middleware.MessageMiddleware',
        'django.middleware.clickjacking.XFrameOptionsMiddleware',
        'simple_history.middleware.HistoryRequestMiddleware', # Simple history
    )
    ALLOWED_HOSTS = ["*"]
    ROOT_URLCONF = 'solar.urls'
    SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
    WSGI_APPLICATION = 'solar.wsgi.application'
    # Email
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    BASE_URL = 'http://localhost:8080'
    EMAIL_HOST = os.getenv('EMAIL_HOST', 'localhost')  # Para MailHog
    EMAIL_PORT = int(os.getenv('EMAIL_PORT', '1025'))  # Para MailHog
    EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
    EMAIL_USE_TLS = strtobool(os.getenv('EMAIL_USE_TLS', 'no'))
    EMAIL_USE_SSL = strtobool(os.getenv('EMAIL_USE_SSL', 'no'))
    DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'noreply@solarenergy.com')
    
    ADMINS = (
        ('Author', 'daviddjustt@gmail.com'),
    )

    # Postgres
    DATABASES = {
        'default': dj_database_url.config(
            default='postgres://postgres:@postgres:5432/postgres',
            conn_max_age=int(os.getenv('POSTGRES_CONN_MAX_AGE', 600))
        )
    }
    # General
    APPEND_SLASH = False
    TIME_ZONE = 'America/Sao_Paulo' # Alterado para o fuso horário correto
    LANGUAGE_CODE = 'pt-br' # Alterado para o idioma português do Brasil
    # If you set this to False, Django will make some optimizations so as not
    # to load the internationalization machinery.
    USE_I18N = True # Ativado para suporte à internacionalização
    USE_L10N = True
    USE_TZ = True
    LOGIN_REDIRECT_URL = '/'
    # Static files (CSS, JavaScript, Images)
    # https://docs.djangoproject.com/en/2.0/howto/static-files/
    STATIC_ROOT = os.path.normpath(join(os.path.dirname(BASE_DIR), 'static'))
    STATICFILES_DIRS = []
    STATIC_URL = '/static/'
    STATICFILES_FINDERS = (
        'django.contrib.staticfiles.finders.FileSystemFinder',
        'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    )
    # Media files
    MEDIA_ROOT = join(os.path.dirname(BASE_DIR), 'media')
    MEDIA_URL = '/media/'
    TEMPLATES = [
        {
            'BACKEND': 'django.template.backends.django.DjangoTemplates',
            'DIRS': [
                os.path.join(BASE_DIR, 'templates'),
                os.path.join(BASE_DIR, 'solar', 'templates'),  # ADICIONAR esta linha
            ],
            'APP_DIRS': True,
            'OPTIONS': {
                'context_processors': [
                    'django.template.context_processors.debug',
                    'django.template.context_processors.request',
                    'django.contrib.auth.context_processors.auth',
                    'django.contrib.messages.context_processors.messages',
                ],
            },
        },
    ]
    # Set DEBUG to False as a default for safety
    # https://docs.djangoproject.com/en/dev/ref/settings/#debug
    DEBUG = strtobool(os.getenv('DJANGO_DEBUG', 'no'))
    # Password Validation
    # https://docs.djangoproject.com/en/2.0/topics/auth/passwords/#module-django.contrib.auth.password_validation
    AUTH_PASSWORD_VALIDATORS = [
        {
            'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
        },
        {
            'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        },
        {
            'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
        },
        {
            'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
        },
    ]
    SPECTACULAR_SETTINGS = {
        'TITLE': 'solar API',
        'DESCRIPTION': 'Documentação da API do projeto solar',
        'VERSION': '1.0.0',
        'SERVE_INCLUDE_SCHEMA': False,
        'SECURITY': [{'Bearer': []}],
        'COMPONENT_SPLIT_REQUEST': True,
        'SCHEMA_PATH_PREFIX': '/api/v1/',
        'SWAGGER_UI_SETTINGS': {
            'deepLinking': True,
            'persistAuthorization': True,
            'displayOperationId': True,
        },
    }
    # Logging
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'django.server': {
                '()': 'django.utils.log.ServerFormatter',
                'format': '[%(server_time)s] %(message)s',
            },
            'verbose': {
                'format': '%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s'
            },
            'simple': {
                'format': '%(levelname)s %(message)s'
            },
        },
        'filters': {
            'require_debug_true': {
                '()': 'django.utils.log.RequireDebugTrue',
            },
        },
        'handlers': {
            'django.server': {
                'level': 'INFO',
                'class': 'logging.StreamHandler',
                'formatter': 'django.server',
            },
            'console': {
                'level': 'DEBUG',
                'class': 'logging.StreamHandler',
                'formatter': 'simple'
            },
            'mail_admins': {
                'level': 'ERROR',
                'class': 'django.utils.log.AdminEmailHandler'
            }
        },
        'loggers': {
            'django': {
                'handlers': ['console'],
                'propagate': True,
            },
            'django.server': {
                'handlers': ['django.server'],
                'level': 'INFO',
                'propagate': False,
            },
            'django.request': {
                'handlers': ['mail_admins', 'console'],
                'level': 'ERROR',
                'propagate': False,
            },
            'django.db.backends': {
                'handlers': ['console'],
                'level': 'INFO'
            },
            'django.core.mail': {
                'handlers': ['console'],
                'level': 'DEBUG',
                'propagate': True,
            },
            'solar.users.email': {
                'handlers': ['console'],
                'level': 'DEBUG',
                'propagate': True,
            },
            'solar.users.views': {
                'handlers': ['console'],
                'level': 'INFO',
                'propagate': True,
            },
        }
    }
    # Custom user app
    AUTH_USER_MODEL = 'users.User'
    # Authentication backends - com CPF e email
    AUTHENTICATION_BACKENDS = [
        'solar.users.backends.EmailOrCPFBackend',  # Backend customizado
        'django.contrib.auth.backends.ModelBackend',   # Backend padrão como fallback
    ]
    # Djoser Settings
    DJOSER = {

        'LOGIN_FIELD': 'email',
        'USER_CREATE_PASSWORD_RETYPE': True,
        'USERNAME_CHANGED_EMAIL_CONFIRMATION': True,
        'PASSWORD_CHANGED_EMAIL_CONFIRMATION': True,
        'SEND_CONFIRMATION_EMAIL': True,
        'SET_PASSWORD_RETYPE': True,
        'SET_USERNAME_RETYPE': True,
        'PASSWORD_RESET_CONFIRM_URL': 'password/reset/confirm/{uid}/{token}',
        'USERNAME_RESET_CONFIRM_URL': 'email/reset/confirm/{uid}/{token}',
        'ACTIVATION_URL': 'activate/{uid}/{token}',
        'SEND_ACTIVATION_EMAIL': True,
        'SERIALIZERS': {
            'user_create': 'solar.users.serializers.UserCreateSerializer',
            'user': 'solar.users.serializers.UserSerializer',
            'current_user': 'solar.users.serializers.UserSerializer',
            'user_update': 'solar.users.serializers.UserUpdateSerializer',
            'token_create': 'solar.users.serializers.SpecialCPFTokenCreateSerializer',
        },
        'PERMISSIONS': {
            'user': ['rest_framework.permissions.IsAuthenticated'],
            'user_list': ['rest_framework.permissions.IsAdminUser'],
            'user_delete': ['rest_framework.permissions.IsAdminUser'],
            'user_create': ['rest_framework.permissions.AllowAny'],
            'user_update': ['rest_framework.permissions.IsAuthenticated'],
        },
        'EMAIL': {
            'activation': 'solar.users.email.ActivationEmail',
            'confirmation': 'solar.users.email.ConfirmationEmail',
            'password_reset': 'solar.users.email.PasswordResetEmail',
            'password_changed_confirmation': 'solar.users.email.PasswordChangedConfirmationEmail',
            'username_changed_confirmation': 'solar.users.email.UsernameChangedConfirmationEmail',
            'username_reset': 'solar.users.email.UsernameResetEmail',
            
        }
    }
    SIMPLE_JWT = {
        "AUTH_HEADER_TYPES": ("Bearer",),
        "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
        "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
        "ROTATE_REFRESH_TOKENS": True, # Rotaciona tokens de refresh
        "BLACKLIST_AFTER_ROTATION": True,# Adiciona tokens antigos à blacklist
        "UPDATE_LAST_LOGIN": True,# Atualiza timestamp de último login
    }
    CORS_ALLOWED_ORIGINS = [
        "http://127.0.0.1:3000",
        "http://localhost:3000",  # ADICIONAR
        "http://127.0.0.1:8080",  # ADICIONAR (backend)
        "http://localhost:8080",  # ADICIONAR (backend)
    ]
    CORS_ALLOW_CREDENTIALS = True

    CORS_ALLOWED_HEADERS = [
        'accept',
        'accept-encoding',
        'authorization',
        'content-type',
        'dnt',
        'origin',
        'user-agent',
        'x-csrftoken',
        'x-requested-with',
    ]

    REST_FRAMEWORK = {
        'DEFAULT_AUTHENTICATION_CLASSES': (
            'rest_framework_simplejwt.authentication.JWTAuthentication',
            'rest_framework.authentication.TokenAuthentication',
            'rest_framework.authentication.SessionAuthentication',
        ),
        'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
        'DEFAULT_PERMISSION_CLASSES': [
            'rest_framework.permissions.IsAuthenticated',
        ],
    }

    # Configurações para URLs e nome do site
    SITE_NAME = os.getenv('SITE_NAME', 'SolarEnergy')
    SITE_URL = os.getenv('SITE_URL', 'http://localhost:8080')  # Backend URL
    FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')  # ADICIONAR
    DOMAIN = os.getenv('DOMAIN', 'localhost:8080')  # ADICIONAR
