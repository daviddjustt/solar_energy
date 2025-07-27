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
        'rest_framework',
        'rest_framework.authtoken',
        'djangorestframework_camel_case',
        'django_filters',
        'drf_spectacular',
        'corsheaders',
        'djoser',
        'rest_framework_simplejwt.token_blacklist',
        'import_export',
        'simple_history',  # ADICIONADO - estava faltando
        
        # Your apps
        'solar.users',
        'solar.documents',
    )

    MIDDLEWARE = (
        'django.middleware.security.SecurityMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        'corsheaders.middleware.CorsMiddleware',
        'django.middleware.common.CommonMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
        'django.contrib.messages.middleware.MessageMiddleware',
        'django.middleware.clickjacking.XFrameOptionsMiddleware',
        'simple_history.middleware.HistoryRequestMiddleware',
    )

    ALLOWED_HOSTS = ["*"]
    ROOT_URLCONF = 'solar.urls'
    SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
    WSGI_APPLICATION = 'solar.wsgi.application'

    # Email
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    BASE_URL = os.getenv('BASE_URL', 'http://localhost:8080')
    EMAIL_HOST = os.getenv('EMAIL_HOST', 'mailhog')  # Corrigido para mailhog
    EMAIL_PORT = int(os.getenv('EMAIL_PORT', '1025'))
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
    TIME_ZONE = 'America/Sao_Paulo'
    LANGUAGE_CODE = 'pt-br'
    USE_I18N = True
    USE_L10N = True
    USE_TZ = True
    LOGIN_REDIRECT_URL = '/'

    # Static files
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
                os.path.join(BASE_DIR, 'solar', 'templates'),
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

    DEBUG = strtobool(os.getenv('DJANGO_DEBUG', 'no'))

    # Password Validation
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

    # CORRIGIDO - Configuração do DRF Spectacular
    SPECTACULAR_SETTINGS = {
        'TITLE': 'Solar API',
        'DESCRIPTION': 'Documentação da API do projeto Solar',
        'VERSION': '1.0.0',
        'SERVE_INCLUDE_SCHEMA': False,
        'SWAGGER_UI_SETTINGS': {
            'deepLinking': True,
            'persistAuthorization': True,
            'displayOperationId': True,
        },
        'COMPONENT_SPLIT_REQUEST': True,
        'SCHEMA_PATH_PREFIX': '/api/v1/',
        'SECURITY': [{'Bearer': []}],
        # Configurações de compatibilidade com Django 5.1+
        'ENUM_NAME_OVERRIDES': {},
        'POSTPROCESSING_HOOKS': [],
        'PREPROCESSING_HOOKS': [],
        'DISABLE_ERRORS_AND_WARNINGS': False,
    }

    # Logging (mantido como estava)
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

    # Authentication backends
    AUTHENTICATION_BACKENDS = [
        'solar.users.backends.EmailOrCPFBackend',
        'django.contrib.auth.backends.ModelBackend',
    ]

    # Djoser Settings (mantido como estava)
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

    # Simple JWT
    SIMPLE_JWT = {
        "AUTH_HEADER_TYPES": ("Bearer",),
        "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
        "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
        "ROTATE_REFRESH_TOKENS": True,
        "BLACKLIST_AFTER_ROTATION": True,
        "UPDATE_LAST_LOGIN": True,
        'USER_ID_FIELD': 'uuid',
        'USER_ID_CLAIM': 'user_id',
    }

    # CORS
    CORS_ALLOWED_ORIGINS = [
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:8080",
        "http://localhost:8080",
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

    # CORRIGIDO - Configuração do Django REST Framework
    REST_FRAMEWORK = {
        'DEFAULT_AUTHENTICATION_CLASSES': [
            'rest_framework_simplejwt.authentication.JWTAuthentication',
            'rest_framework.authentication.TokenAuthentication',
            'rest_framework.authentication.SessionAuthentication',
        ],
        'DEFAULT_PARSER_CLASSES': [
            'djangorestframework_camel_case.parser.CamelCaseFormParser',
            'djangorestframework_camel_case.parser.CamelCaseMultiPartParser',
            'djangorestframework_camel_case.parser.CamelCaseJSONParser',
        ],
        'DEFAULT_RENDERER_CLASSES': [
            'djangorestframework_camel_case.render.CamelCaseJSONRenderer',
            'djangorestframework_camel_case.render.CamelCaseBrowsableAPIRenderer',
            'rest_framework.renderers.JSONRenderer',
        ],
        'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
        'DEFAULT_PERMISSION_CLASSES': [
            'rest_framework.permissions.IsAuthenticated',
        ],
        'DEFAULT_FILTER_BACKENDS': [
            'django_filters.rest_framework.DjangoFilterBackend',
        ],
        'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
        'PAGE_SIZE': 20,
    }

    # Site configurations
    SITE_NAME = os.getenv('SITE_NAME', 'SolarEnergy')
    SITE_URL = os.getenv('SITE_URL', 'http://localhost:8080')
    FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')
    DOMAIN = os.getenv('DOMAIN', 'localhost:8080')

# Configuração para desenvolvimento
class Local(Common):
    """
    Configuração para ambiente de desenvolvimento local
    """
    DEBUG = True
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    
    # Configurações específicas para desenvolvimento
    CORS_ALLOW_ALL_ORIGINS = True  # Apenas para desenvolvimento
    
    # Logging mais verboso para desenvolvimento
    LOGGING = {
        **Common.LOGGING,
        'loggers': {
            **Common.LOGGING['loggers'],
            'django.db.backends': {
                'handlers': ['console'],
                'level': 'DEBUG',  # Mostra queries SQL
            },
        }
    }

# Configuração para produção
class Production(Common):
    """
    Configuração para ambiente de produção
    """
    DEBUG = False
    
    # Configurações de segurança para produção
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_REDIRECT_EXEMPT = []
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
