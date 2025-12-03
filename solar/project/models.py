# Em solar/models.py (ou onde você define seus modelos principais)

from django.db import models
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
import uuid # Para o UUIDField do User

# Importe suas classes TextChoices e utilitários
from solar.choices import (
    AndamentoDoProjeto,
    TipoDocumento,
    StatusDocumento,
    VoltagemSistema
)

class Projeto(models.Model): # Renomeado de ClientProject para Projeto
    """
    Representa um projeto de energia solar.
    """
    id = models.AutoField(primary_key=True) # PK INTEGER conforme o esquema
    codigoCliente = models.CharField(
        max_length=50,
        unique=True, # UNIQUE conforme o esquema
        verbose_name="Código único do cliente",
        help_text="Código identificador único para o cliente associado ao projeto."
    )
    created_by = models.ForeignKey(
        'users.User', # Referência ao seu modelo User customizado
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_projects',
        verbose_name='Usuário que criou o projeto'
    )
    nomeTitular = models.CharField(
        max_length=200,
        verbose_name="Nome do titular do projeto"
    )
    classe = models.CharField(
        max_length=100,
        verbose_name="Classe do projeto (ex: Residencial, Comercial)"
    )
    voltagem = models.CharField( # ENUM no esquema, CharField com choices no Django
        max_length=100, # Ajuste o max_length se os valores em VOLTAGEM_CHOICES forem maiores
        choices=VoltagemSistema.choices,
        verbose_name="Voltagem do sistema",
        help_text="Voltagem nominal do sistema de energia solar."
    )

    # Status e Documentação
    documetacaoCompleta = models.BooleanField(
        default=False,
        verbose_name="Documentação completa",
        help_text="Indica se toda a documentação obrigatória do projeto foi enviada e aprovada."
    )
    status = models.CharField( # ENUM no esquema, CharField com choices no Django
        max_length=43, # Ajuste o max_length para o maior valor de AndamentoDoProjeto
        choices=AndamentoDoProjeto.choices,
        default=AndamentoDoProjeto.ANALISE_DE_DOCUMENTOS,
        verbose_name="Status do Projeto"
    )

    # Metadados (assumindo que BaseModel não é usado diretamente aqui, mas os campos são similares)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Data de Criação")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Última Atualização")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Projeto"
        verbose_name_plural = "Projetos"

    def __str__(self):
        return f"Projeto {self.codigoCliente} - {self.nomeTitular}"

    @property
    def created_by_name(self):
        """Retorna o nome do usuário que criou o projeto."""
        return self.created_by.name if self.created_by else "Usuário não identificado"

    @property
    def created_by_uuid(self):
        """Retorna o UUID do usuário que criou o projeto."""
        return str(self.created_by.uuid) if self.created_by else None

    def get_required_documents(self):
        """
        Retorna uma lista dos tipos de documentos obrigatórios para este projeto.
        Esta lista pode ser dinâmica com base em regras de negócio (ex: PF vs PJ).
        """
        # Exemplo de documentos obrigatórios (usando a classe TipoDocumento)
        required_docs = [
            TipoDocumento.DOCUMENTO_CLIENTE.value,
            TipoDocumento.UNIDADES_CONSUMIDORAS_FATURA.value,
            TipoDocumento.LISTA_MATERIAL.value,
            TipoDocumento.PROCURACAO.value,
            TipoDocumento.ART.value,
            TipoDocumento.TRT.value,
        ]
        # Adicione documentos específicos para PJ se o cliente for PJ
        if self.documentos_contato.tipoDocumento == TipoDocumento.PESSOA_JURIDICA.value: # Acessando via related_name
            required_docs.extend([
                TipoDocumento.CARTAO_CNPJ.value,
                TipoDocumento.INSCRICAO_ESTADUAL.value,
                TipoDocumento.CONTRATO_SOCIAL.value,
            ])
        return required_docs

    def check_documetacaoCompleta(self):
        """
        Verifica se toda a documentação obrigatória foi enviada E APROVADA
        para este projeto e atualiza o campo `documetacaoCompleta`.
        """
        required_docs = self.get_required_documents()
        # Acessa os documentos relacionados via related_name 'documents' do ProjectDocument
        uploaded_approved_doc_types = set(
            self.documents.filter(status=StatusDocumento.APROVADO)
            .values_list('document_type', flat=True)
        )
        self.documetacaoCompleta = all(doc_type in uploaded_approved_doc_types for doc_type in required_docs)
        self.save(update_fields=['documetacaoCompleta', 'updated_at']) # Salva apenas o campo atualizado e updated_at
