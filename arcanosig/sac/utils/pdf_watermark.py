import io
import os
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

def add_watermark_to_pdf(original_pdf_path, user_cpf):
    """
    Aplica uma marca d'água com apenas os 3 primeiros e 2 últimos números do CPF
    em múltiplas linhas horizontais e verticais para cobrir dinamicamente cada página do PDF.
    """
    try:
        with open(original_pdf_path, "rb") as original_file:
            original_pdf_reader = PdfReader(original_file)
            output_writer = PdfWriter()
            
            # Extrai apenas os números do CPF
            cpf_numbers_only = ''.join(filter(str.isdigit, user_cpf))
            if not cpf_numbers_only or len(cpf_numbers_only) < 11:
                print("Erro: CPF inválido ou incompleto")
                return None
            
            # Cria CPF mascarado: 3 primeiros + XXXXXX + 2 últimos
            masked_cpf = cpf_numbers_only[:3] + "XXXXXX" + cpf_numbers_only[-2:]
            texto = masked_cpf
            
            print(f"CPF mascarado para marca d'água: {texto}")
            
            # Processa cada página individualmente
            for page_num, page in enumerate(original_pdf_reader.pages):
                # Obtém as dimensões reais da página atual
                page_width = float(page.mediabox.width)
                page_height = float(page.mediabox.height)
                print(f"Página {page_num + 1}: {page_width:.1f} x {page_height:.1f} pontos")
                
                # Calcula parâmetros dinâmicos baseados no tamanho da página
                watermark_page = create_dynamic_watermark(texto, page_width, page_height)
                
                # Aplica a marca d'água na página atual
                page.merge_page(watermark_page)
                output_writer.add_page(page)
            
            # Salva o resultado
            output_stream = io.BytesIO()
            output_writer.write(output_stream)
            output_stream.seek(0)
            
            print(f"Marca d'água aplicada com sucesso em {len(original_pdf_reader.pages)} página(s).")
            return output_stream
            
    except FileNotFoundError:
        print(f"Erro: Arquivo não encontrado: {original_pdf_path}")
        return None
    except Exception as e:
        print(f"Erro ao processar PDF: {e}")
        return None
    
def create_dynamic_watermark(texto, page_width, page_height):
    """
    Cria uma marca d'água dinâmica baseada nas dimensões da página.
    Args:
        texto (str): Texto da marca d'água
        page_width (float): Largura da página em pontos
        page_height (float): Altura da página em pontos
    Returns:
        PdfPage: Página com a marca d'água
    """
    # Cria buffer para a marca d'água
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=(page_width, page_height))
    # Calcula parâmetros dinâmicos baseados no tamanho da página
    font_size = calculate_optimal_font_size(page_width, page_height)
    spacing_x, spacing_y = calculate_optimal_spacing(texto, font_size, page_width, page_height)
    print(f" Fonte: {font_size}, Espaçamento: {spacing_x}x{spacing_y}")
    # Configurações da marca d'água
    a = 0.6 # Variável que define a cor dos caracteres 0 ( preto ) -> 1 ( branco )
    can.setFillColor((a, a, a))
    can.setFillAlpha(0.6)
    can.setFont("Helvetica", font_size)
    # Calcula margens para garantir cobertura total
    margin_x = spacing_x
    margin_y = spacing_y
    # Padrão principal - grade regular
    draw_watermark_pattern(can, texto, page_width, page_height, spacing_x, spacing_y, margin_x, margin_y)
    can.save()
    packet.seek(0)
    # Retorna a página da marca d'água
    watermark_reader = PdfReader(packet)
    return watermark_reader.pages[0] if watermark_reader.pages else None

def calculate_optimal_font_size(page_width, page_height):
    """
    Calcula o tamanho ideal da fonte baseado nas dimensões da página.
    """
    # Tamanho base para página carta (612x792)
    base_width, base_height = 612, 792
    base_font_size = 12
    # Calcula fator de escala baseado na área da página
    page_area = page_width * page_height
    base_area = base_width * base_height
    scale_factor = (page_area / base_area) ** 0.5
    # Aplica limites mínimo e máximo
    font_size = base_font_size * scale_factor
    return max(8, min(20, int(font_size)))

def calculate_optimal_spacing(texto, font_size, page_width, page_height):
    """
    Calcula o espaçamento ideal baseado no texto, fonte e dimensões da página.
    """
    # Estima largura do texto (aproximação)
    char_width = font_size * 0.6 # Aproximação para Helvetica
    text_width = len(texto) * char_width
    # Calcula espaçamentos proporcionais
    # Espaçamento horizontal: largura do texto + margem proporcional
    spacing_x = int(text_width * 2.5)
    # Espaçamento vertical: altura da fonte + margem proporcional
    spacing_y = int(font_size * 3.5)
    # Ajusta baseado no tamanho da página para garantir densidade adequada
    min_repetitions_x = max(5, int(page_width / 150)) # Mínimo 8 repetições por linha
    min_repetitions_y = max(8, int(page_height / 80)) # Mínimo 12 linhas
    spacing_x = min(spacing_x, int(page_width / min_repetitions_x))
    spacing_y = min(spacing_y, int(page_height / min_repetitions_y))
    return spacing_x, spacing_y

def draw_watermark_pattern(can, texto, page_width, page_height, spacing_x, spacing_y,
                          margin_x, margin_y, offset_x=0, offset_y=0):
    """
    Desenha o padrão de marca d'água na página.
    """
    start_x = -margin_x + offset_x
    end_x = int(page_width) + margin_x + offset_x
    start_y = -margin_y + offset_y
    end_y = int(page_height) + margin_y + offset_y
    for y in range(start_y, end_y, spacing_y):
        for x in range(start_x, end_x, spacing_x):
            can.drawString(x, y, texto)
          
