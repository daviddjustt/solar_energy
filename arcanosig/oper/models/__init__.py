# Import e exporta os modelos para facilitar importações de outros módulos

# Enums
from arcanosig.oper.models.enums import (
    OperacaoStatus,
    TipoEquipamento,
    StatusEquipamento,
    StatusAceite,
    ModeloVeiculo,
    TipoNotificacao
)

# Operações
from arcanosig.oper.models.operacao import (
    Operacao,
    Guarnicao,
    GuarnicaoMembro
)

# Veículos
from arcanosig.oper.models.veiculo import (
    Veiculo,
    FotoVeiculo,
    Abastecimento
)

# Cautelas
from arcanosig.oper.models.cautela import (
    CautelaIndividual,
    ItemCautela,
    AceiteCautela
)

# Notificações
from arcanosig.oper.models.notificacao import (
    Notificacao
)

# Lista de todos os modelos para facilitar importações
__all__ = [
    # Enums
    'OperacaoStatus',
    'TipoEquipamento',
    'StatusEquipamento',
    'StatusAceite',
    'ModeloVeiculo',
    'TipoNotificacao',

    # Operações
    'Operacao',
    'Guarnicao',
    'GuarnicaoMembro',

    # Veículos
    'Veiculo',
    'FotoVeiculo',
    'Abastecimento',

    # Cautelas
    'CautelaIndividual',
    'ItemCautela',
    'AceiteCautela',

    # Notificações
    'Notificacao'
]
