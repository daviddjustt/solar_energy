VOLTAGEM_MAP = {
    '127': 'Monofásico - 127V',
    '220': 'Monofásico - 220V',
    '127/220': 'Bifásico - 127/220V',
    '220/380': 'Bifásico - 220/380V',
    '127/220T': 'Trifásico - 127/220V',
    '220/380T': 'Trifásico - 220/380V',
}

def convert_voltage_value_to_label(value):
    """
    Converte o value do SelectItem em label

    Exemplos:
        "127" → "Monofásico - 127V"
        "220/380" → "Bifásico - 220/380V"
        "127/220T" → "Trifásico - 127/220V"
    """
    value_str = str(value).strip()
    return VOLTAGEM_MAP.get(value_str, value_str)
