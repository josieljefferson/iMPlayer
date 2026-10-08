#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
=============================================================
        MEDIA DOWNLOADER - PLAYLISTS M3U E EPG XMLTV
=============================================================

Baixa automaticamente:

PLAYLISTS:
    playlists/playlist.m3u
    playlists/playlists.m3u

EPG:
    epg/playlist.xml.gz
    epg/playlists.xml.gz

iMPLAYER:
    iMPlayer/playlist.m3u
    iMPlayer/playlists.m3u
    iMPlayer/playlist.xml.gz
    iMPlayer/playlists.xml.gz

RAIZ:
    playlist.m3u
    playlists.m3u

Características:

    - Downloads paralelos
    - Retry automático
    - Backoff exponencial
    - Arquivo temporário durante download
    - Substituição atômica
    - Validação de tamanho
    - Validação de GZIP
    - MD5
    - Logs detalhados
    - Falha do processo se nenhum arquivo for baixado
    - Não adiciona timestamp dentro dos arquivos
    - Não corrompe arquivos XML.GZ
=============================================================
"""

import gzip
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import md5

import requests


# =============================================================
# CONFIGURAÇÕES
# =============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Connection": "keep-alive",
}


OUTPUT_DIRS = {
    "playlists": os.path.join(
        os.getcwd(),
        "playlists",
    ),

    "epg": os.path.join(
        os.getcwd(),
        "epg",
    ),

    "implayer": os.path.join(
        os.getcwd(),
        "iMPlayer",
    ),

    "root": os.getcwd(),
}


TIMEOUT = 30

RETRIES = 3

MAX_WORKERS = 5

MIN_FILE_SIZE = 1024

MAX_FILE_SIZE_MB = 100

CHUNK_SIZE = 64 * 1024


# =============================================================
# LOGGING
# =============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(
            "media_downloader.log",
            encoding="utf-8",
        ),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)


# =============================================================
# VALIDAÇÃO DE URL
# =============================================================

def validate_url(url):
    """
    Verifica se a URL utiliza HTTP ou HTTPS.
    """

    if not isinstance(url, str):

        logger.error(
            "URL inválida: tipo %s",
            type(url).__name__,
        )

        return False

    url = url.strip()

    if not url:

        logger.error(
            "URL vazia."
        )

        return False

    if not url.startswith(
        (
            "http://",
            "https://",
        )
    ):

        logger.error(
            "URL sem HTTP/HTTPS: %s",
            url,
        )

        return False

    return True


# =============================================================
# CRIAR DIRETÓRIO
# =============================================================

def create_directory(directory):
    """
    Cria o diretório caso ele não exista.

    Não apaga arquivos existentes.
    """

    try:

        os.makedirs(
            directory,
            exist_ok=True,
        )

        logger.info(
            "Diretório pronto: %s",
            directory,
        )

        return True

    except Exception as error:

        logger.error(
            "Falha ao criar diretório %s: %s",
            directory,
            error,
        )

        return False


# =============================================================
# LIMPAR TEMPORÁRIOS
# =============================================================

def clean_temp_files():
    """
    Remove somente arquivos .tmp deixados por downloads
    interrompidos anteriormente.
    """

    for directory in (
        OUTPUT_DIRS["playlists"],
        OUTPUT_DIRS["epg"],
        OUTPUT_DIRS["implayer"],
    ):

        if not os.path.isdir(directory):
            continue

        for filename in os.listdir(directory):

            if not filename.endswith(".tmp"):
                continue

            path = os.path.join(
                directory,
                filename,
            )

            try:

                os.remove(path)

                logger.info(
                    "Temporário removido: %s",
                    path,
                )

            except OSError as error:

                logger.warning(
                    "Não foi possível remover %s: %s",
                    path,
                    error,
                )


# =============================================================
# HASH MD5
# =============================================================

def calculate_file_hash(file_path):
    """
    Calcula MD5 do arquivo.
    """

    try:

        hash_md5 = md5()

        with open(
            file_path,
            "rb",
        ) as file:

            for chunk in iter(
                lambda: file.read(8192),
                b"",
            ):

                hash_md5.update(chunk)

        return hash_md5.hexdigest()

    except Exception as error:

        logger.error(
            "Erro ao calcular MD5 de %s: %s",
            file_path,
            error,
        )

        return None


# =============================================================
# TAMANHO DO ARQUIVO
# =============================================================

def verify_file_size(file_path):
    """
    Verifica tamanho mínimo e máximo.
    """

    try:

        size = os.path.getsize(
            file_path
        )

        max_size = (
            MAX_FILE_SIZE_MB
            * 1024
            * 1024
        )

        if size < MIN_FILE_SIZE:

            logger.error(
                "Arquivo muito pequeno: %s (%d bytes)",
                file_path,
                size,
            )

            return False

        if size > max_size:

            logger.error(
                "Arquivo muito grande: %s (%.2f MB)",
                file_path,
                size / 1024 / 1024,
            )

            return False

        return True

    except Exception as error:

        logger.error(
            "Erro verificando tamanho de %s: %s",
            file_path,
            error,
        )

        return False


# =============================================================
# VALIDAR M3U
# =============================================================

def validate_m3u(file_path):
    """
    Verifica se o arquivo M3U possui conteúdo válido.
    """

    try:

        with open(
            file_path,
            "r",
            encoding="utf-8-sig",
            errors="replace",
        ) as file:

            first_line = file.readline().strip()

        if not first_line.startswith(
            "#EXTM3U"
        ):

            logger.error(
                "M3U inválido: %s",
                file_path,
            )

            return False

        return True

    except Exception as error:

        logger.error(
            "Erro validando M3U %s: %s",
            file_path,
            error,
        )

        return False


# =============================================================
# VALIDAR GZIP
# =============================================================

def validate_gzip(file_path):
    """
    Verifica se o arquivo .gz é realmente um GZIP válido.
    """

    try:

        with gzip.open(
            file_path,
            "rb",
        ) as file:

            while file.read(
                1024 * 1024
            ):

                pass

        return True

    except Exception as error:

        logger.error(
            "GZIP inválido: %s: %s",
            file_path,
            error,
        )

        return False


# =============================================================
# VALIDAR ARQUIVO PELO TIPO
# =============================================================

def validate_downloaded_file(file_path):
    """
    Executa validações específicas.
    """

    if not os.path.exists(
        file_path
    ):

        logger.error(
            "Arquivo não existe: %s",
            file_path,
        )

        return False

    if not verify_file_size(
        file_path
    ):

        return False

    lower_path = file_path.lower()

    if lower_path.endswith(
        ".m3u"
    ):

        return validate_m3u(
            file_path
        )

    if lower_path.endswith(
        ".xml.gz"
    ):

        return validate_gzip(
            file_path
        )

    return True


# =============================================================
# DOWNLOAD
# =============================================================

def download_file(
    url,
    save_path,
    retries=RETRIES,
):
    """
    Faz o download usando arquivo temporário.

    O arquivo final só é substituído depois que o download
    e todas as validações forem concluídos.
    """

    if not validate_url(url):
        return False

    directory = os.path.dirname(
        save_path
    )

    os.makedirs(
        directory,
        exist_ok=True,
    )

    temp_path = (
        save_path
        + ".tmp"
    )

    for attempt in range(
        1,
        retries + 1,
    ):

        try:

            logger.info(
                "Download %d/%d: %s",
                attempt,
                retries,
                url,
            )

            with requests.get(
                url,
                headers=HEADERS,
                timeout=TIMEOUT,
                stream=True,
                allow_redirects=True,
            ) as response:

                response.raise_for_status()

                with open(
                    temp_path,
                    "wb",
                ) as file:

                    for chunk in response.iter_content(
                        chunk_size=CHUNK_SIZE
                    ):

                        if chunk:
                            file.write(chunk)

            # -------------------------------------------------
            # VALIDAR TEMPORÁRIO
            # -------------------------------------------------

            if not validate_downloaded_file(
                temp_path
            ):

                logger.error(
                    "Arquivo baixado inválido: %s",
                    temp_path,
                )

                try:
                    os.remove(temp_path)
                except OSError:
                    pass

                continue

            # -------------------------------------------------
            # SUBSTITUIÇÃO ATÔMICA
            # -------------------------------------------------

            os.replace(
                temp_path,
                save_path,
            )

            # -------------------------------------------------
            # INFORMAÇÕES
            # -------------------------------------------------

            file_size = os.path.getsize(
                save_path
            )

            file_hash = calculate_file_hash(
                save_path
            )

            logger.info(
                "DOWNLOAD OK: %s",
                save_path,
            )

            logger.info(
                "Tamanho: %d bytes",
                file_size,
            )

            logger.info(
                "MD5: %s",
                file_hash,
            )

            return True

        except requests.exceptions.Timeout:

            logger.error(
                "Timeout: %s",
                url,
            )

        except requests.exceptions.ConnectionError as error:

            logger.error(
                "Erro de conexão: %s",
                error,
            )

        except requests.exceptions.HTTPError as error:

            logger.error(
                "Erro HTTP: %s",
                error,
            )

        except requests.exceptions.RequestException as error:

            logger.error(
                "Erro de requisição: %s",
                error,
            )

        except Exception as error:

            logger.error(
                "Erro inesperado: %s: %s",
                type(error).__name__,
                error,
            )

        # -----------------------------------------------------
        # REMOVER TEMPORÁRIO
        # -----------------------------------------------------

        if os.path.exists(
            temp_path
        ):

            try:
                os.remove(temp_path)
            except OSError:
                pass

        # -----------------------------------------------------
        # BACKOFF
        # -----------------------------------------------------

        if attempt < retries:

            wait_time = 2 ** attempt

            logger.info(
                "Aguardando %d segundos antes da próxima tentativa...",
                wait_time,
            )

            time.sleep(
                wait_time
            )

    logger.error(
        "FALHA DEFINITIVA: %s",
        url,
    )

    return False


# =============================================================
# LISTA DE DOWNLOADS
# =============================================================

def get_download_lists():
    """
    Retorna todas as URLs utilizadas pelo sistema.
    """

    playlists = {
        "playlist.m3u":
            "https://raw.githubusercontent.com/"
            "josieljefferson/EPG/refs/heads/main/"
            "output/playlist.m3u",

        "playlists.m3u":
            "https://raw.githubusercontent.com/"
            "josieljefferson/EPG-M3U/refs/heads/main/"
            "output/playlist.m3u",
    }

    epg_files = {
        "playlist.xml.gz":
            "https://raw.githubusercontent.com/"
            "josieljefferson/EPG/refs/heads/main/"
            "output/epg.xml.gz",

        "playlists.xml.gz":
            "https://raw.githubusercontent.com/"
            "josieljefferson/EPG-M3U/refs/heads/main/"
            "output/epg.xml.gz",
    }

    return playlists, epg_files


# =============================================================
# CONSTRUIR TAREFAS
# =============================================================

def build_download_tasks():
    """
    Monta todas as tarefas.

    As mesmas fontes são utilizadas nas respectivas pastas.
    """

    playlists, epg_files = (
        get_download_lists()
    )

    tasks = []

    # ---------------------------------------------------------
    # PLAYLISTS
    # ---------------------------------------------------------

    for filename, url in playlists.items():

        tasks.append(
            (
                url,
                os.path.join(
                    OUTPUT_DIRS["playlists"],
                    filename,
                ),
            )
        )

        tasks.append(
            (
                url,
                os.path.join(
                    OUTPUT_DIRS["implayer"],
                    filename,
                ),
            )

        tasks.append(
            (
                url,
                os.path.join(
                    OUTPUT_DIRS["root"],
                    filename,
                ),
            )
        )

    # ---------------------------------------------------------
    # EPG
    # ---------------------------------------------------------

    for filename, url in epg_files.items():

        tasks.append(
            (
                url,
                os.path.join(
                    OUTPUT_DIRS["epg"],
                    filename,
                ),
            )
        )

        tasks.append(
            (
                url,
                os.path.join(
                    OUTPUT_DIRS["implayer"],
                    filename,
                ),
            )
        )

    return tasks


# =============================================================
# PREPARAR DIRETÓRIOS
# =============================================================

def prepare_directories():
    """
    Cria as pastas necessárias sem apagar os arquivos atuais.
    """

    for name in (
        "playlists",
        "epg",
        "implayer",
    ):

        directory = OUTPUT_DIRS[
            name
        ]

        if not create_directory(
            directory
        ):

            raise RuntimeError(
                "Não foi possível preparar "
                f"o diretório: {directory}"
            )


# =============================================================
# PRINCIPAL
# =============================================================

def main():

    logger.info(
        "=" * 70
    )

    logger.info(
        "INICIANDO MEDIA DOWNLOADER"
    )

    logger.info(
        "=" * 70
    )

    start_time = time.time()

    # ---------------------------------------------------------
    # PREPARAÇÃO
    # ---------------------------------------------------------

    prepare_directories()

    clean_temp_files()

    # ---------------------------------------------------------
    # TAREFAS
    # ---------------------------------------------------------

    tasks = build_download_tasks()

    logger.info(
        "Total de downloads: %d",
        len(tasks),
    )

    logger.info(
        "Threads: %d",
        MAX_WORKERS,
    )

    # ---------------------------------------------------------
    # EXECUTAR
    # ---------------------------------------------------------

    success = 0
    failures = 0

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = {
            executor.submit(
                download_file,
                url,
                path,
            ): (
                url,
                path,
            )

            for url, path in tasks
        }

        for future in as_completed(
            futures
        ):

            url, path = futures[
                future
            ]

            try:

                if future.result():

                    success += 1

                else:

                    failures += 1

            except Exception as error:

                failures += 1

                logger.error(
                    "Erro na tarefa %s: %s",
                    path,
                    error,
                )

    # ---------------------------------------------------------
    # RELATÓRIO
    # ---------------------------------------------------------

    elapsed = (
        time.time()
        - start_time
    )

    logger.info(
        "=" * 70
    )

    logger.info(
        "PROCESSO CONCLUÍDO"
    )

    logger.info(
        "Tempo: %.2f segundos",
        elapsed,
    )

    logger.info(
        "Sucessos: %d",
        success,
    )

    logger.info(
        "Falhas: %d",
        failures,
    )

    logger.info(
        "=" * 70
    )

    # ---------------------------------------------------------
    # LISTAGEM FINAL
    # ---------------------------------------------------------

    for name in (
        "playlists",
        "epg",
        "implayer",
    ):

        directory = OUTPUT_DIRS[
            name
        ]

        logger.info(
            "Conteúdo de %s:",
            directory,
        )

        if not os.path.isdir(
            directory
        ):
            continue

        for filename in sorted(
            os.listdir(directory)
        ):

            path = os.path.join(
                directory,
                filename,
            )

            if os.path.isfile(
                path
            ):

                logger.info(
                    "  %s - %d bytes",
                    filename,
                    os.path.getsize(path),
                )

    # ---------------------------------------------------------
    # FALHAR SE NÃO HOUVE DOWNLOAD
    # ---------------------------------------------------------

    if success == 0:

        logger.critical(
            "NENHUM ARQUIVO FOI BAIXADO."
        )

        raise SystemExit(1)

    # ---------------------------------------------------------
    # DOWNLOAD PARCIAL
    # ---------------------------------------------------------

    if failures > 0:

        logger.warning(
            "Alguns downloads falharam."
        )

        # Não derruba o workflow se pelo menos um arquivo
        # foi baixado corretamente.
        return

    logger.info(
        "TODOS OS DOWNLOADS FORAM CONCLUÍDOS."
    )


# =============================================================
# EXECUÇÃO
# =============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        logger.warning(
            "Processo interrompido pelo usuário."
        )

        raise SystemExit(130)

    except Exception as error:

        logger.critical(
            "Erro não tratado: %s",
            error,
            exc_info=True,
        )

        raise SystemExit(1)
