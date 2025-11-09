# solar/documents/utils.py

VOLTAGEM_MAP = {
    '127': 'Monofásico - 127V',
    '220': 'Monofásico - 220V',
    '127/220': 'Bifásico - 127/220V',
    '220/380': 'Bifásico - 220/380V',
    '127/220T': 'Trifásico - 127/220V',
    '220/380T': 'Trifásico - 220/380V',
}
# Versão com os labels exatos
VOLTAGEM_LABELS = [
    'Monofásico - 127V',
    'Monofásico - 220V',
    'Bifásico - 127/220V',
    'Bifásico - 220/380V',
    'Trifásico - 127/220V',
    'Trifásico - 220/380V',
]

def convert_voltage_value_to_label(value):
    """Converte value em label"""
    value_str = str(value).strip()
    return VOLTAGEM_MAP.get(value_str, value_str)

def get_voltage_choices():
    """Retorna as choices para o model"""
    return [(label, label) for label in VOLTAGEM_LABELS]
