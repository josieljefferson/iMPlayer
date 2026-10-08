#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import shutil
import requests
from hashlib import md5
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configurações globais
HEADERS = {"User-Agent": "Mozilla/5.0"}
OUTPUT_DIR = os.path.join(os.getcwd(), "playlists")
TIMEOUT = 10
RETRIES = 3
MAX_WORKERS = 5


def validate_url(url):
    """
    Valida a URL antes de tentar o download.
    """
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        logger.error(f"URL inválida: {url}")
        return False

    return True


def download_file(url, save_path, retries=RETRIES):
    """
    Baixa um arquivo da URL fornecida e sobrescreve
    o arquivo de destino se ele já existir.
    """

    if not validate_url(url):
        return False

    for attempt in range(1, retries + 1):
        try:
            logger.info(
                f"Tentativa {attempt} de {retries}: "
                f"Baixando arquivo de: {url}"
            )

            response = requests.get(
                url,
                headers=HEADERS,
                timeout=TIMEOUT
            )

            if response.status_code == 200:
                # Garante que o diretório de destino exista
                os.makedirs(
                    os.path.dirname(save_path),
                    exist_ok=True
                )

                # Salva o conteúdo do arquivo
                with open(save_path, "wb") as file:
                    file.write(response.content)

                # Verifica se o arquivo foi salvo corretamente
                file_size = os.path.getsize(save_path)

                if file_size > 0:
                    logger.info(
                        f"Arquivo salvo com sucesso: "
                        f"{save_path} "
                        f"(Tamanho: {file_size} bytes)"
                    )

                    # Calcula o hash MD5
                    with open(save_path, "rb") as file:
                        file_hash = md5(file.read()).hexdigest()

                    logger.info(
                        f"Hash MD5 do arquivo: {file_hash}"
                    )

                    return True

                logger.error(
                    f"Erro: arquivo vazio ou corrompido: {save_path}"
                )

            else:
                logger.error(
                    f"Falha ao baixar {url}. "
                    f"Código HTTP: {response.status_code}"
                )

        except requests.exceptions.Timeout:
            logger.error(
                f"Erro de timeout ao baixar {url}"
            )

        except requests.exceptions.ConnectionError:
            logger.error(
                f"Erro de conexão ao baixar {url}"
            )

        except requests.exceptions.RequestException as e:
            logger.error(
                f"Erro HTTP ao baixar {url}: {e}"
            )

        except Exception as e:
            logger.error(
                f"Erro inesperado ao baixar {url}: {e}"
            )

    logger.error(
        f"Falha ao baixar {url} após {retries} tentativas."
    )

    return False


def main():
    # Remove a pasta playlists antes de baixar os arquivos
    logger.info("Limpando diretório anterior...")

    shutil.rmtree(
        OUTPUT_DIR,
        ignore_errors=True
    )

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    # Lista de arquivos para download
    #
    # IMPORTANTE:
    # Cada item agora possui:
    #   nome do arquivo -> URL
    #
    # Isso corrige o erro:
    # AttributeError: 'list' object has no attribute 'items'

    files_to_download = {
        "m3u": {
            "EPG-playlist.m3u":
                "https://raw.githubusercontent.com/"
                "josieljefferson/EPG/refs/heads/main/"
                "output/playlist.m3u",

            "EPG-M3U-playlist.m3u":
                "https://raw.githubusercontent.com/"
                "josieljefferson/EPG-M3U/refs/heads/main/"
                "output/playlist.m3u"
        },

        "xml.gz": {
            "EPG-epg.xml.gz":
                "https://raw.githubusercontent.com/"
                "josieljefferson/EPG/refs/heads/main/"
                "output/epg.xml.gz",

            "EPG-M3U-epg.xml.gz":
                "https://raw.githubusercontent.com/"
                "josieljefferson/EPG-M3U/refs/heads/main/"
                "output/epg.xml.gz"
        }
    }

    # Processa os downloads
    logger.info("Iniciando download dos arquivos...")

    download_results = []

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = []

        for _, files in files_to_download.items():

            for filename, url in files.items():

                save_path = os.path.join(
                    OUTPUT_DIR,
                    filename
                )

                future = executor.submit(
                    download_file,
                    url,
                    save_path
                )

                futures.append(
                    (filename, url, future)
                )

        # Aguarda todos os downloads
        for filename, url, future in futures:

            try:
                success = future.result()

                download_results.append(success)

                if not success:
                    logger.error(
                        f"Falha no download: {filename}"
                    )

            except Exception as e:
                logger.error(
                    f"Erro no download de {filename}: {e}"
                )

                download_results.append(False)

    # Resultado final
    total = len(download_results)
    successful = sum(download_results)
    failed = total - successful

    logger.info(
        f"Download concluído: "
        f"{successful}/{total} arquivo(s) baixado(s)."
    )

    if failed > 0:
        logger.error(
            f"{failed} arquivo(s) apresentaram falha."
        )

        # Faz o GitHub Actions falhar se algum download falhar
        raise RuntimeError(
            "Um ou mais arquivos não foram baixados corretamente."
        )


if __name__ == "__main__":
    main()
