#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SCRIPT DE DOWNLOAD DE PLAYISTS M3U E ARQUIVOS EPG (XMLTV) - VERSÃO 1.2
Autor: [josielluz]
Data: [31/07/2025]

Melhorias desta versão:
1. Controle preciso de sobrescrita de arquivos
2. Verificação de arquivos existentes
3. Logs detalhados de cada operação
4. Tratamento robusto de erros
5. Downloads paralelos otimizados
"""

# ==============================================
# IMPORTAÇÕES DE BIBLIOTECAS
# ==============================================

import os               # Operações com sistema de arquivos
import shutil           # Operações avançadas com arquivos
import requests         # Para requisições HTTP
from hashlib import md5 # Para cálculo de hash MD5
import logging          # Sistema de logs
from concurrent.futures import ThreadPoolExecutor, as_completed  # Paralelismo
import time             # Para medir tempo de execução

# ==============================================
# CONFIGURAÇÕES GLOBAIS
# ==============================================

# Cabeçalhos HTTP para simular navegador
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# Estrutura de diretórios de saída
OUTPUT_DIRS = {
    "playlists": os.path.join(os.getcwd(), "playlists"),  # Playlists padrão
    "epg": os.path.join(os.getcwd(), "epg"),              # Guias de programação
    "implayer": os.path.join(os.getcwd(), "iMPlayer"),    # Versão iMPlayer
    "root": os.getcwd()                                   # Pasta raiz
}

# Configurações de rede
TIMEOUT = 20              # Tempo limite em segundos para requisições
RETRIES = 3               # Número de tentativas por download
MAX_WORKERS = 5           # Número máximo de threads paralelas
MIN_FILE_SIZE = 1024      # Tamanho mínimo válido (1KB)
MAX_FILE_SIZE_MB = 50     # Tamanho máximo (50MB)

# ==============================================
# CONFIGURAÇÃO DO SISTEMA DE LOG
# ==============================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("download_manager.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==============================================
# FUNÇÕES AUXILIARES (VERIFICAÇÕES E VALIDAÇÕES)
# ==============================================

def validate_url(url):
    """Valida se uma URL é válida e segura para download.
    
    Args:
        url (str): URL a ser validada
        
    Returns:
        bool: True se válida, False caso contrário
    """
    if not isinstance(url, str):
        logger.error(f"URL inválida (tipo incorreto): {type(url)}")
        return False
    
    url = url.strip()
    if not url:
        logger.error("URL vazia")
        return False
        
    if not url.startswith(('http://', 'https://')):
        logger.error(f"URL sem protocolo HTTP/HTTPS: {url}")
        return False
        
    return True

def create_directory(dir_path):
    """Cria um diretório garantindo que esteja vazio.
    
    Args:
        dir_path (str): Caminho do diretório
        
    Returns:
        bool: True se bem-sucedido, False caso contrário
    """
    try:
        # Remove diretório existente se houver
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path)
            logger.info(f"Diretório limpo: {dir_path}")
            
        # Cria novo diretório
        os.makedirs(dir_path, exist_ok=True)
        logger.info(f"Diretório criado: {dir_path}")
        return True
        
    except Exception as e:
        logger.error(f"Falha ao criar diretório {dir_path}: {str(e)}")
        return False

def calculate_file_hash(file_path):
    """Calcula hash MD5 de um arquivo para verificação.
    
    Args:
        file_path (str): Caminho do arquivo
        
    Returns:
        str: Hash MD5 ou None em caso de erro
    """
    try:
        hash_md5 = md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        logger.error(f"Erro ao calcular hash: {str(e)}")
        return None

def verify_file_size(file_path):
    """Verifica se o arquivo está dentro dos limites de tamanho.
    
    Args:
        file_path (str): Caminho do arquivo
        
    Returns:
        bool: True se o tamanho for válido
    """
    try:
        size = os.path.getsize(file_path)
        max_size = MAX_FILE_SIZE_MB * 1024 * 1024
        
        if size < MIN_FILE_SIZE:
            logger.error(f"Arquivo muito pequeno: {size} bytes")
            return False
        elif size > max_size:
            logger.error(f"Arquivo muito grande: {size/1024/1024:.2f}MB")
            return False
        return True
    except Exception as e:
        logger.error(f"Erro ao verificar tamanho: {str(e)}")
        return False

# ==============================================
# FUNÇÃO PRINCIPAL DE DOWNLOAD
# ==============================================

def download_file(url, save_path, retries=RETRIES):
    """Baixa um arquivo com tratamento de erros robusto.
    
    Args:
        url (str): URL do arquivo
        save_path (str): Caminho local para salvar
        retries (int): Número de tentativas
        
    Returns:
        bool: True se bem-sucedido, False caso contrário
    """
    # Validação inicial
    if not validate_url(url):
        return False
        
    # Garante que o diretório pai existe
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    
    # Tentativas de download
    for attempt in range(1, retries + 1):
        try:
            logger.info(f"Tentativa {attempt}/{retries} - URL: {url}")
            
            # Download com stream para arquivos grandes
            with requests.get(url, headers=HEADERS, timeout=TIMEOUT, stream=True) as r:
                r.raise_for_status()
                
                # Salva em arquivo temporário primeiro
                temp_path = save_path + '.tmp'
                with open(temp_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            
                # Verificações pós-download
                if not os.path.exists(temp_path):
                    logger.error("Arquivo temporário não criado")
                    continue
                    
                if not verify_file_size(temp_path):
                    os.remove(temp_path)
                    continue
                    
                # Renomeia para o nome final (operação atômica)
                if os.path.exists(save_path):
                    os.remove(save_path)
                os.rename(temp_path, save_path)
                
                # Log de sucesso
                file_size = os.path.getsize(save_path)
                file_hash = calculate_file_hash(save_path)
                logger.info(f"Download OK: {save_path} ({file_size} bytes) | Hash: {file_hash}")
                return True
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro HTTP: {type(e).__name__} - {str(e)}")
        except Exception as e:
            logger.error(f"Erro inesperado: {type(e).__name__} - {str(e)}")
            
        # Espera antes de tentar novamente
        if attempt < retries:
            time.sleep(2 ** attempt)  # Backoff exponencial
            
    logger.error(f"Falha após {retries} tentativas: {url}")
    return False

# ==============================================
# LISTAS DE ARQUIVOS PARA DOWNLOAD
# ==============================================

def get_download_lists():
    """Retorna dicionários com todos os arquivos a serem baixados.
    
    Returns:
        tuple: (playlists, epg_files, implayer_files, root_files)
    """
    # Playlists principais
    playlists = {
        "playlist.m3u": "https://raw.githubusercontent.com/josieljefferson/EPG/refs/heads/main/output/playlist.m3u",
        "playlists.m3u": "https://raw.githubusercontent.com/josieljefferson/EPG-M3U/refs/heads/main/output/playlist.m3u"
    }
    
    # Arquivos EPG (guias de programação)
    epg_files = {
        "playlist.xml.gz": "https://raw.githubusercontent.com/josieljefferson/EPG/refs/heads/main/output/epg.xml.gz",
        "playlists.xml.gz": "https://raw.githubusercontent.com/josieljefferson/EPG-M3U/refs/heads/main/output/epg.xml.gz"
    }
    
    # Versão para iMPlayer
    implayer_files = {
        "playlist.m3u": "https://raw.githubusercontent.com/josieljefferson/EPG/refs/heads/main/output/playlist.m3u",
        "playlists.m3u": "https://raw.githubusercontent.com/josieljefferson/EPG-M3U/refs/heads/main/output/playlist.m3u",
        "playlist.xml.gz": "https://raw.githubusercontent.com/josieljefferson/EPG/refs/heads/main/output/epg.xml.gz",
        "playlists.xml.gz": "https://raw.githubusercontent.com/josieljefferson/EPG-M3U/refs/heads/main/output/epg.xml.gz"
    }
    
    # Arquivos para a raiz (cópia das principais playlists)
    root_files = {
        "playlist.m3u": "https://raw.githubusercontent.com/josieljefferson/EPG/refs/heads/main/output/playlist.m3u",
        "playlists.m3u": "https://raw.githubusercontent.com/josieljefferson/EPG-M3U/refs/heads/main/output/playlist.m3u"
    }
    
    return playlists, epg_files, implayer_files, root_files

# ==============================================
# FUNÇÃO PRINCIPAL DO PROGRAMA
# ==============================================

def main():
    """Função principal que orquestra todo o processo."""
    logger.info("Iniciando processo de download")
    start_time = time.time()
    
    # 1. Preparação dos diretórios
    logger.info("Preparando estrutura de diretórios...")
    for dir_name, dir_path in OUTPUT_DIRS.items():
        if dir_name != "root":  # Não limpa a raiz
            if not create_directory(dir_path):
                logger.critical(f"Falha ao preparar {dir_name}")
                return
        else:
            os.makedirs(dir_path, exist_ok=True)
    
    # 2. Obter listas de download
    playlists, epg_files, implayer_files, root_files = get_download_lists()
    
    # 3. Configurar todas as tarefas de download
    download_tasks = []
    
    # Playlists principais (pasta playlists e raiz)
    for filename, url in playlists.items():
        download_tasks.append((url, os.path.join(OUTPUT_DIRS["playlists"], filename)))
        download_tasks.append((url, os.path.join(OUTPUT_DIRS["root"], filename)))
    
    # Arquivos EPG
    for filename, url in epg_files.items():
        download_tasks.append((url, os.path.join(OUTPUT_DIRS["epg"], filename)))
    
    # iMPlayer
    for filename, url in implayer_files.items():
        download_tasks.append((url, os.path.join(OUTPUT_DIRS["implayer"], filename)))
    
    # Arquivos específicos para raiz
    for filename, url in root_files.items():
        download_tasks.append((url, os.path.join(OUTPUT_DIRS["root"], filename)))
    
    # 4. Executar downloads em paralelo
    logger.info(f"Iniciando {len(download_tasks)} downloads com {MAX_WORKERS} threads...")
    success = 0
    failures = 0
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(download_file, url, path): (url, path) for url, path in download_tasks}
        
        for future in as_completed(futures):
            url, path = futures[future]
            try:
                if future.result():
                    success += 1
                else:
                    failures += 1
            except Exception as e:
                logger.error(f"Erro durante download: {str(e)}")
                failures += 1
    
    # 5. Relatório final
    elapsed = time.time() - start_time
    logger.info(f"Processo concluído em {elapsed:.2f} segundos")
    logger.info(f"Resultado: {success} sucessos, {failures} falhas")
    
    if failures > 0:
        logger.warning("Alguns downloads falharam. Verifique os logs.")
    else:
        logger.info("Todos os downloads foram concluídos com sucesso!")

# Ponto de entrada
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Processo interrompido pelo usuário")
    except Exception as e:
        logger.critical(f"Erro não tratado: {str(e)}", exc_info=True)
    finally:
        logger.info("Script finalizado")
