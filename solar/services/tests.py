from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from django.urls import reverse

from solar.services.models import ServiceType

User = get_user_model()

class ExternalUserCreationTestCase(APITestCase):
    def setUp(self):
        # 1. Configurar o Administrador
        self.admin = User.objects.create_superuser(
            email='admin@teste.com',
            name='Administrador Chefe',
            password='123',
            celular='79999999999'
        )
        
        # 2. Configurar um Cliente comum
        self.cliente = User.objects.create_user(
            email='cliente@teste.com',
            name='Cliente Teste',
            password='123',
            celular='79999999999',
            cpf='11111111111'
        )
        
        # 3. Criar um Serviço para vincular ao Externo
        self.tipo_servico = ServiceType.objects.create(
            codigo="ligacao_nova", 
            nome="Ligação Nova", 
            valor=20.00, 
            prazo_informativo="1 dia", 
            ativo=True
        )
        
        # URL do router (caso tenha registrado como external-users sem basename explícito, o DRF cria 'user-list')
        # Ajuste a URL abaixo se o seu basename for diferente
        self.url = '/api/v1/users/external-users/'
        
    def test_admin_consegue_criar_usuario_externo(self):
        """Testa se o Admin cria o usuário e se as flags são forçadas corretamente."""
        self.client.force_authenticate(user=self.admin)
        
        payload = {
            "email": "parceiro@teste.com",
            "name": "Parceiro Executor da Silva",
            "celular": "79999999999",
            "cpf": "12345678901",
            "password": "SenhaForte123!",
            "tipos_servico": [self.tipo_servico.id]
        }
        
        response = self.client.post(self.url, payload, format='json')
        
        # Verifica se criou com sucesso
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Busca o usuário criado no banco
        created_user = User.objects.get(email="parceiro@teste.com")
        
        # Verifica se as regras do Proxy Model foram aplicadas
        self.assertTrue(created_user.is_externo)
        self.assertFalse(created_user.is_cliente)
        self.assertFalse(created_user.is_admin)
        self.assertFalse(created_user.is_tecnico)
        self.assertFalse(created_user.is_pessoa_juridica)
        
        # Verifica se o serviço foi vinculado
        self.assertIn(self.tipo_servico, created_user.tipos_servico.all())
        
        # Verifica se a senha foi salva corretamente (não pode ser texto puro)
        self.assertNotEqual(created_user.password, "SenhaForte123!")
        self.assertTrue(created_user.check_password("SenhaForte123!"))

    def test_cliente_nao_pode_criar_externo(self):
        """Testa se a permissão IsAdminOrSuperuser está bloqueando clientes."""
        self.client.force_authenticate(user=self.cliente)
        
        payload = {
            "email": "hacker@teste.com",
            "name": "Invasor",
            "celular": "79999999999",
            "password": "123"
        }
        
        response = self.client.post(self.url, payload, format='json')
        
        # Deve retornar 403 Forbidden
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)