#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script unificado para download de playlists M3U e arquivos EPG (XMLTV)
Autor: [Seu Nome]
Data: [Data]
Versão: 1.0

Descrição:
Este script combina funcionalidades de três scripts anteriores para:
1. Baixar múltiplas playlists M3U de diversas fontes
2. Baixar arquivos EPG (guia de programação) em formato XML comprimido
3. Gerenciar downloads paralelos com verificação de integridade
4. Manter logs detalhados de todas as operações
"""

# Importação de bibliotecas necessárias
import os           # Para operações com arquivos e diretórios
import shutil       # Para operações avançadas com arquivos
import requests     # Para fazer requisições HTTP
from hashlib import md5  # Para gerar hash MD5 de verificação
import logging      # Para registro de logs
from concurrent.futures import ThreadPoolExecutor, as_completed  # Para downloads paralelos

# ==============================================
# CONFIGURAÇÕES GLOBAIS
# ==============================================

# Cabeçalho HTTP para simular navegador
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# Diretórios de saída para diferentes tipos de conteúdo
OUTPUT_DIRS = {
    "playlists": os.path.join(os.getcwd(), "playlists"),  # Para arquivos M3U
    "epg": os.path.join(os.getcwd(), "epg"),            # Para arquivos EPG
    "implayer": os.path.join(os.getcwd(), "iMPlayer")     # Para versão iMPlayer
}

# Configurações de rede
TIMEOUT = 15          # Tempo limite em segundos para requisições
RETRIES = 3           # Número de tentativas para cada download
MAX_WORKERS = 5       # Número máximo de downloads paralelos
MAX_FILE_SIZE = 100   # Tamanho mínimo em bytes para considerar o download válido (100MB)

# ==============================================
# CONFIGURAÇÃO DO SISTEMA DE LOGGING
# ==============================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("media_downloader.log"),  # Log em arquivo
        logging.StreamHandler()                        # Log no console
    ]
)
logger = logging.getLogger(__name__)

# ==============================================
# FUNÇÕES AUXILIARES
# ==============================================

def validate_url(url):
    """
    Valida se a URL é válida e segura para download.
    
    Parâmetros:
        url (str): URL a ser validada
        
    Retorna:
        bool: True se a URL é válida, False caso contrário
    """
    if not isinstance(url, str):
        logger.error(f"URL inválida (não é string): {url}")
        return False
        
    url = url.strip()
    if not url:
        logger.error("URL vazia")
        return False
        
    if not url.startswith(("http://", "https://")):
        logger.error(f"URL deve começar com http:// ou https://: {url}")
        return False
        
    return True

def create_directory(dir_path):
    """
    Cria um diretório se ele não existir, limpando-o se já existir.
    
    Parâmetros:
        dir_path (str): Caminho do diretório a ser criado/limpo
        
    Retorna:
        bool: True se o diretório está pronto para uso, False em caso de erro
    """
    try:
        # Remove o diretório existente se houver
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path)
            logger.info(f"Diretório limpo: {dir_path}")
            
        # Cria o novo diretório
        os.makedirs(dir_path, exist_ok=True)
        logger.info(f"Diretório criado: {dir_path}")
        return True
        
    except Exception as e:
        logger.error(f"Falha ao preparar diretório {dir_path}: {str(e)}")
        return False

def calculate_file_hash(file_path, hash_type='md5'):
    """
    Calcula o hash de um arquivo para verificação de integridade.
    
    Parâmetros:
        file_path (str): Caminho do arquivo
        hash_type (str): Tipo de hash a ser calculado (md5, sha1, etc)
        
    Retorna:
        str: Hash calculado ou None em caso de erro
    """
    if not os.path.exists(file_path):
        logger.error(f"Arquivo não encontrado para cálculo de hash: {file_path}")
        return None
        
    try:
        hash_obj = md5() if hash_type == 'md5' else None
        if not hash_obj:
            logger.error(f"Tipo de hash não suportado: {hash_type}")
            return None
            
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):  # Lê em pedaços para arquivos grandes
                hash_obj.update(chunk)
                
        return hash_obj.hexdigest()
        
    except Exception as e:
        logger.error(f"Erro ao calcular hash para {file_path}: {str(e)}")
        return None

# ==============================================
# FUNÇÃO PRINCIPAL DE DOWNLOAD
# ==============================================

def download_file(url, save_path, retries=RETRIES, timeout=TIMEOUT):
    """
    Faz o download de um arquivo com tratamento de erros e múltiplas tentativas.
    
    Parâmetros:
        url (str): URL do arquivo a ser baixado
        save_path (str): Caminho local para salvar o arquivo
        retries (int): Número de tentativas em caso de falha
        timeout (int): Tempo limite em segundos para a requisição
        
    Retorna:
        bool: True se o download foi bem-sucedido, False caso contrário
    """
    # Validação inicial
    if not validate_url(url):
        return False
        
    # Verifica se o diretório de destino existe
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    
    # Tentativas de download
    for attempt in range(1, retries + 1):
        try:
            logger.info(f"Tentativa {attempt}/{retries}: Baixando {url}")
            
            # Faz a requisição HTTP com stream para arquivos grandes
            with requests.get(url, headers=HEADERS, timeout=timeout, stream=True) as response:
                response.raise_for_status()  # Levanta exceção para códigos 4xx/5xx
                
                # Salva o conteúdo no arquivo local
                with open(save_path, 'wb') as file:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:  # Filtra chunks keep-alive
                            file.write(chunk)
                            
                # Verificação pós-download
                if not os.path.exists(save_path):
                    logger.error(f"Arquivo não foi criado: {save_path}")
                    continue
                    
                file_size = os.path.getsize(save_path)
                if file_size < MAX_FILE_SIZE:
                    logger.error(f"Arquivo muito pequeno (possível erro): {file_size} bytes")
                    os.remove(save_path)
                    continue
                    
                # Calcula e registra o hash do arquivo
                file_hash = calculate_file_hash(save_path)
                if file_hash:
                    logger.info(f"Download concluído: {save_path} ({file_size} bytes) | Hash: {file_hash}")
                    return True
                    
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro na tentativa {attempt}: {type(e).__name__} - {str(e)}")
        except Exception as e:
            logger.error(f"Erro inesperado na tentativa {attempt}: {type(e).__name__} - {str(e)}")
            
    logger.error(f"Falha ao baixar após {retries} tentativas: {url}")
    return False

# ==============================================
# LISTAS DE DOWNLOAD
# ==============================================

def get_download_lists():
    """
    Retorna dicionários com os arquivos a serem baixados, organizados por tipo.
    
    Retorna:
        tuple: (playlists, epg_files, implayer_files)
    """
    # Playlists M3U padrão
    playlists = {
        "playlist.m3u": "https://raw.githubusercontent.com/josieljefferson/EPG/refs/heads/main/output/playlist.m3u",
        "playlists.m3u": "https://raw.githubusercontent.com/josieljefferson/EPG-M3U/refs/heads/main/output/playlist.m3u"
    }
    
    # Arquivos EPG (XMLTV)
    epg_files = {
        "playlist.xml.gz": "https://raw.githubusercontent.com/josieljefferson/EPG/refs/heads/main/output/epg.xml.gz",
        "playlists.xml.gz": "https://raw.githubusercontent.com/josieljefferson/EPG-M3U/refs/heads/main/output/epg.xml.gz"
    }
    
    # Versão para iMPlayer (nomes padronizados)
    implayer_files = {
        "playlist.m3u": "https://raw.githubusercontent.com/josieljefferson/EPG/refs/heads/main/output/playlist.m3u",
        "playlists.m3u": "https://raw.githubusercontent.com/josieljefferson/EPG-M3U/refs/heads/main/output/playlist.m3u",
        "playlist.xml.gz": "https://raw.githubusercontent.com/josieljefferson/EPG/refs/heads/main/output/epg.xml.gz",
        "playlists.xml.gz": "https://raw.githubusercontent.com/josieljefferson/EPG-M3U/refs/heads/main/output/epg.xml.gz"
    }
    
    return playlists, epg_files, implayer_files

# ==============================================
# FUNÇÃO PRINCIPAL
# ==============================================

def main():
    """
    Função principal que orquestra todo o processo de download.
    """
    logger.info("Iniciando script de download de playlists e EPGs")
    
    # 1. Preparação dos diretórios
    logger.info("Preparando diretórios de saída...")
    for dir_name, dir_path in OUTPUT_DIRS.items():
        if not create_directory(dir_path):
            logger.error(f"Não foi possível preparar o diretório {dir_name}. Abortando.")
            return
            
    # 2. Obter listas de download
    playlists, epg_files, implayer_files = get_download_lists()
    
    # 3. Configurar tarefas de download
    download_tasks = [
        (playlists, OUTPUT_DIRS["playlists"]),
        (epg_files, OUTPUT_DIRS["epg"]),
        (implayer_files, OUTPUT_DIRS["implayer"])
    ]
    
    # 4. Executar downloads em paralelo
    logger.info("Iniciando downloads paralelos...")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        
        for files_dict, output_dir in download_tasks:
            for filename, url in files_dict.items():
                save_path = os.path.join(output_dir, filename)
                futures.append(executor.submit(download_file, url, save_path))
                
        # Monitorar progresso e resultados
        success_count = 0
        fail_count = 0
        
        for future in as_completed(futures):
            if future.result():
                success_count += 1
            else:
                fail_count += 1
                
    # 5. Relatório final
    logger.info(f"Downloads concluídos. Sucessos: {success_count}, Falhas: {fail_count}")
    
    if fail_count > 0:
        logger.warning("Alguns downloads falharam. Verifique os logs para detalhes.")
        
    logger.info("Processo finalizado.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Script interrompido pelo usuário.")
    except Exception as e:
        logger.error(f"Erro não tratado: {str(e)}", exc_info=True)
