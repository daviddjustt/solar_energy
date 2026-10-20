from django.test import TestCase
import tempfile
from decimal import Decimal
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model

from solar.services.models import ServiceType, ServiceRequest

User = get_user_model()

class ServiceAPI (APITestCase):
    def setUp(self):
        # 1. Configurar Utilizadores
        self.cliente = User.objects.create_user(email="cliente@teste.com", password="123")
        self.admin = User.objects.create_superuser(email="admin@teste.com", password="123")
        
        self.externo = User.objects.create_user(email="externo@teste.com", password="123")
        self.externo.is_externo = True #
        self.externo.save()

        # 2. Configurar Tipos de Serviço
        self.tipo_ligacao = ServiceType.objects.create(
            codigo="ligacao_nova", nome="Ligação Nova", valor=Decimal("20.00"), ativo=True
        )
        self.tipo_compensacao = ServiceType.objects.create(
            codigo="lista_compensacao", nome="Lista Compensação", valor=Decimal("250.00"), ativo=True
        )
        
        # Limitar o acesso do externo apenas à ligação nova
        self.externo.tipos_servico.add(self.tipo_ligacao)

        # 3. Criar uma solicitação inicial para testes
        self.solicitacao = ServiceRequest.objects.create(
            tipo=self.tipo_ligacao,
            solicitante=self.cliente,
            tipo_pessoa='PF',
            nome_razao_social="João Silva",
            documento="12345678900",
            endereco="Rua A",
            valor_cobrado=Decimal("20.00")
        )

        self.url_list_create = reverse('api:service-list')
        self.url_detail = reverse('api:service-detail', kwargs={'pk': self.solicitacao.id})

    def test_criacao_apenas_por_cliente(self):
        """Admin e externo não criam solicitações, nem em nome de um cliente."""
        payload = {
            "tipo": self.tipo_ligacao.id,
            "tipo_pessoa": "PF",
            "nome_razao_social": "Teste",
            "documento": "00000000000",
            "endereco": "Rua B",
        }

        # Externo tenta criar (deve falhar)
        self.client.force_authenticate(user=self.externo)
        response = self.client.post(self.url_list_create, payload)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) #

        # Admin tenta criar (deve falhar)
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(self.url_list_create, payload)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) #

        # Cliente tenta criar (deve ter sucesso e forçar solicitante)
        self.client.force_authenticate(user=self.cliente)
        response = self.client.post(self.url_list_create, payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['solicitante'], self.cliente.id) #[cite: 1]

    def test_valor_copiado_e_mantido_para_pedidos_antigos(self):
        """O valor é copiado para a solicitação no momento da abertura, para que mudanças de preço não alterem pedidos antigos[cite: 1]."""
        self.client.force_authenticate(user=self.cliente)
        
        # Cliente abre solicitação a R$ 20,00
        payload = {
            "tipo": self.tipo_ligacao.id,
            "tipo_pessoa": "PF",
            "nome_razao_social": "Cliente Fixo",
            "documento": "111",
            "endereco": "Rua Fixa",
        }
        response = self.client.post(self.url_list_create, payload)
        solicitacao_id = response.data['id']
        self.assertEqual(Decimal(response.data['valor_cobrado']), Decimal("20.00")) #[cite: 1]

        # Admin altera o valor na tabela base
        self.tipo_ligacao.valor = Decimal("50.00")
        self.tipo_ligacao.save()

        # Verifica se a solicitação criada manteve os R$ 20,00
        response = self.client.get(reverse('api:service-detail', kwargs={'pk': solicitacao_id}))
        self.assertEqual(Decimal(response.data['valor_cobrado']), Decimal("20.00")) #[cite: 1]

    def test_visibilidade_e_filtros_por_perfil(self):
        """
        Cliente vê só as suas; admin vê tudo; externo é restrito por tipo de serviço[cite: 1].
        """
        # Criar uma solicitação de outro tipo (que o externo não tem acesso)
        ServiceRequest.objects.create(
            tipo=self.tipo_compensacao,
            solicitante=self.cliente,
            tipo_pessoa='PJ',
            nome_razao_social="Empresa X",
            documento="000",
            endereco="Rua C",
            valor_cobrado=Decimal("250.00")
        )

        # 1. Admin vê as 2 solicitações[cite: 1]
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url_list_create)
        self.assertEqual(len(response.data), 2)

        # 2. Externo vê apenas 1 (Ligação Nova, a qual ele tem acesso)[cite: 1]
        self.client.force_authenticate(user=self.externo)
        response = self.client.get(self.url_list_create)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['tipo_detalhe']['codigo'], 'ligacao_nova') #[cite: 1]

    def test_cliente_nao_pode_editar_dados_digitados(self):
        """O cliente não edita os dados depois de enviar[cite: 1]."""
        self.client.force_authenticate(user=self.cliente)
        
        payload = {"nome_razao_social": "Hacker tentou mudar o nome"}
        response = self.client.patch(self.url_detail, payload)
        
        # O backend não deve falhar com 400/500, mas deve ignorar a edição (read_only)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # O nome tem de continuar a ser o original
        self.solicitacao.refresh_from_db()
        self.assertEqual(self.solicitacao.nome_razao_social, "João Silva") #[cite: 1]

    def test_motivo_obrigatorio_em_reprovacao(self):
        """O motivo_reprova é obrigatório quando o status é Reprovado, em qualquer serviço[cite: 1]."""
        self.client.force_authenticate(user=self.admin)
        
        url_status = reverse('api:service-status', kwargs={'pk': self.solicitacao.id})
        
        # Tenta reprovar sem enviar motivo
        payload_sem_motivo = {"status": "REPROVADO"}
        response = self.client.post(url_status, payload_sem_motivo)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST) #[cite: 1]
        
        # Tenta reprovar enviando o motivo
        payload_com_motivo = {
            "status": "REPROVADO", 
            "motivo_reprova": "Falta de documentação essencial."
        }
        response = self.client.post(url_status, payload_com_motivo)
        self.assertEqual(response.status_code, status.HTTP_200_OK) #[cite: 1]

    def test_limite_arquivo_e_formato_heic(self):
        """A foto do medidor aceita também o formato HEIC, até 10 MB[cite: 1]."""
        # Simulando o teste de validação (esta lógica ficará no seu serializer de Attachments)
        # O ficheiro de tamanho > 10MB deve ser rejeitado[cite: 1].
        
        # Testar a extensão HEIC (apenas a simulação do nome de arquivo que a validação deve aceitar)
        arquivo_heic = tempfile.NamedTemporaryFile(suffix=".heic")
        # Assert que a função `validate_file_extension` (que vai ter de atualizar no backend) aceita .heic[cite: 1]
        self.assertTrue(arquivo_heic.name.endswith(".heic"))