#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
=============================================================
              📥 MEDIA DOWNLOADER
=============================================================

Baixa automaticamente:

    • Playlists M3U
    • EPG XML.GZ

Fontes:

    EPG:
    https://raw.githubusercontent.com/josieljefferson/EPG/refs/heads/main/output/playlist.m3u
    https://raw.githubusercontent.com/josieljefferson/EPG/refs/heads/main/output/epg.xml.gz

    EPG-M3U:
    https://raw.githubusercontent.com/josieljefferson/EPG-M3U/refs/heads/main/output/playlist.m3u
    https://raw.githubusercontent.com/josieljefferson/EPG-M3U/refs/heads/main/output/epg.xml.gz

Destinos:

    playlists/
    epg/
    iMPlayer/
    raiz do repositório

Características:

    • Download com streaming
    • Retry automático
    • Timeout
    • Validação M3U
    • Validação GZIP
    • Arquivo temporário
    • Substituição atômica
    • MD5
    • Download paralelo
    • Preserva arquivos válidos em caso de falha
    • Não altera arquivos XML.GZ com texto
    • Não utiliza MY_DOWNLOAD_GITHUB_TOKEN
=============================================================
"""

import gzip
import hashlib
import logging
import os
import time

from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


# ============================================================
# CONFIGURAÇÕES
# ============================================================

BASE_DIR = os.getcwd()

OUTPUT_DIRS = {
    "playlists": os.path.join(BASE_DIR, "playlists"),
    "epg": os.path.join(BASE_DIR, "epg"),
    "implayer": os.path.join(BASE_DIR, "iMPlayer"),
    "root": BASE_DIR,
}

TIMEOUT = 30
RETRIES = 3
MAX_WORKERS = 5

MIN_FILE_SIZE = 1024
MAX_FILE_SIZE_MB = 100
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024

CHUNK_SIZE = 64 * 1024

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Connection": "keep-alive",
}


# ============================================================
# LOGGING
# ============================================================

LOG_FILE = os.path.join(BASE_DIR, "media_downloader.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(
            LOG_FILE,
            encoding="utf-8",
        ),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("media_downloader")


# ============================================================
# VALIDAÇÃO DE URL
# ============================================================

def validate_url(url):
    """Valida minimamente uma URL HTTP/HTTPS."""

    if not isinstance(url, str):
        return False

    url = url.strip()

    return (
        url.startswith("https://")
        or url.startswith("http://")
    )


# ============================================================
# CRIAÇÃO DE DIRETÓRIOS
# ============================================================

def create_directory(directory):
    """Cria o diretório caso ele não exista."""

    try:
        os.makedirs(
            directory,
            exist_ok=True,
        )

        logger.info(
            "Diretório verificado: %s",
            directory,
        )

        return True

    except OSError as exc:
        logger.error(
            "Erro ao criar diretório %s: %s",
            directory,
            exc,
        )

        return False


# ============================================================
# LIMPEZA DE ARQUIVOS TEMPORÁRIOS
# ============================================================

def clean_temp_files():
    """Remove arquivos .tmp antigos."""

    removed = 0

    for root, _, files in os.walk(BASE_DIR):
        for filename in files:

            if not filename.endswith(".tmp"):
                continue

            path = os.path.join(
                root,
                filename,
            )

            try:
                os.remove(path)
                removed += 1

                logger.info(
                    "Arquivo temporário removido: %s",
                    path,
                )

            except OSError as exc:
                logger.warning(
                    "Não foi possível remover %s: %s",
                    path,
                    exc,
                )

    if removed:
        logger.info(
            "Total de arquivos temporários removidos: %d",
            removed,
        )


# ============================================================
# HASH MD5
# ============================================================

def calculate_file_hash(file_path):
    """Calcula MD5 do arquivo."""

    md5 = hashlib.md5()

    try:
        with open(
            file_path,
            "rb",
        ) as file:

            while True:
                chunk = file.read(CHUNK_SIZE)

                if not chunk:
                    break

                md5.update(chunk)

        return md5.hexdigest()

    except OSError as exc:
        logger.error(
            "Erro calculando MD5 de %s: %s",
            file_path,
            exc,
        )

        return None


# ============================================================
# VALIDAÇÃO DO TAMANHO
# ============================================================

def verify_file_size(file_path):
    """Verifica tamanho mínimo e máximo."""

    try:
        size = os.path.getsize(file_path)

    except OSError as exc:
        logger.error(
            "Não foi possível obter tamanho de %s: %s",
            file_path,
            exc,
        )

        return False

    if size < MIN_FILE_SIZE:

        logger.error(
            "Arquivo muito pequeno: %s (%d bytes)",
            file_path,
            size,
        )

        return False

    if size > MAX_FILE_SIZE:

        logger.error(
            "Arquivo excede limite de %d MB: %s",
            MAX_FILE_SIZE_MB,
            file_path,
        )

        return False

    logger.info(
        "Tamanho validado: %s (%d bytes)",
        file_path,
        size,
    )

    return True


# ============================================================
# VALIDAÇÃO M3U
# ============================================================

def validate_m3u(file_path):
    """Valida se o arquivo é uma playlist M3U."""

    try:
        with open(
            file_path,
            "r",
            encoding="utf-8-sig",
            errors="replace",
        ) as file:

            first_line = file.readline().strip()

            if not first_line:
                logger.error(
                    "M3U vazio: %s",
                    file_path,
                )

                return False

            if not first_line.startswith("#EXTM3U"):

                logger.error(
                    "Cabeçalho M3U inválido em %s: %r",
                    file_path,
                    first_line,
                )

                return False

            logger.info(
                "M3U validado: %s",
                file_path,
            )

            return True

    except (
        OSError,
        UnicodeError,
    ) as exc:

        logger.error(
            "Erro validando M3U %s: %s",
            file_path,
            exc,
        )

        return False


# ============================================================
# VALIDAÇÃO GZIP
# ============================================================

def validate_gzip(file_path):
    """
    Valida um arquivo GZIP.

    Importante:
    NÃO adiciona texto ao arquivo depois do download.
    """

    try:
        with gzip.open(
            file_path,
            "rb",
        ) as gz:

            while True:
                chunk = gz.read(CHUNK_SIZE)

                if not chunk:
                    break

        logger.info(
            "GZIP validado: %s",
            file_path,
        )

        return True

    except (
        OSError,
        EOFError,
        gzip.BadGzipFile,
    ) as exc:

        logger.error(
            "GZIP inválido: %s - %s",
            file_path,
            exc,
        )

        return False


# ============================================================
# VALIDAÇÃO GERAL
# ============================================================

def validate_downloaded_file(file_path):
    """Valida arquivo baixado."""

    if not os.path.isfile(file_path):
        logger.error(
            "Arquivo não existe: %s",
            file_path,
        )

        return False

    if not verify_file_size(file_path):
        return False

    lower_path = file_path.lower()

    if lower_path.endswith(".m3u"):

        return validate_m3u(file_path)

    if lower_path.endswith(".xml.gz"):

        return validate_gzip(file_path)

    return True


# ============================================================
# DOWNLOAD
# ============================================================

def download_file(
    url,
    destination,
):
    """
    Faz download de um arquivo.

    O arquivo é baixado para .tmp e somente depois
    substitui o arquivo definitivo.
    """

    if not validate_url(url):

        logger.error(
            "URL inválida: %s",
            url,
        )

        return False

    destination_dir = os.path.dirname(destination)

    if not create_directory(destination_dir):

        return False

    temp_file = destination + ".tmp"

    for attempt in range(
        1,
        RETRIES + 1,
    ):

        try:

            logger.info(
                "Download %d/%d: %s",
                attempt,
                RETRIES,
                url,
            )

            if os.path.exists(temp_file):

                try:
                    os.remove(temp_file)

                except OSError:
                    pass

            with requests.get(
                url,
                headers=HEADERS,
                timeout=TIMEOUT,
                stream=True,
                allow_redirects=True,
            ) as response:

                response.raise_for_status()

                content_length = response.headers.get(
                    "Content-Length"
                )

                if content_length:

                    try:
                        expected_size = int(
                            content_length
                        )

                        if expected_size > MAX_FILE_SIZE:

                            raise ValueError(
                                "Arquivo remoto excede "
                                f"{MAX_FILE_SIZE_MB} MB"
                            )

                    except ValueError as exc:

                        if "excede" in str(exc):

                            raise

                total = 0

                with open(
                    temp_file,
                    "wb",
                ) as file:

                    for chunk in response.iter_content(
                        chunk_size=CHUNK_SIZE
                    ):

                        if not chunk:
                            continue

                        total += len(chunk)

                        if total > MAX_FILE_SIZE:

                            raise ValueError(
                                "Download excedeu o tamanho "
                                f"máximo de {MAX_FILE_SIZE_MB} MB"
                            )

                        file.write(chunk)

            logger.info(
                "Download concluído: %s (%d bytes)",
                url,
                total,
            )

            if not validate_downloaded_file(
                temp_file
            ):

                logger.error(
                    "Arquivo baixado é inválido: %s",
                    url,
                )

                try:
                    os.remove(temp_file)

                except OSError:
                    pass

                raise ValueError(
                    "Arquivo baixado inválido"
                )

            file_hash = calculate_file_hash(
                temp_file
            )

            if file_hash:

                logger.info(
                    "MD5 %s: %s",
                    os.path.basename(destination),
                    file_hash,
                )

            # Substituição atômica.
            os.replace(
                temp_file,
                destination,
            )

            logger.info(
                "Arquivo atualizado: %s",
                destination,
            )

            return True

        except requests.RequestException as exc:

            logger.warning(
                "Erro HTTP no download %d/%d: %s",
                attempt,
                RETRIES,
                exc,
            )

        except (
            OSError,
            ValueError,
        ) as exc:

            logger.warning(
                "Erro no download %d/%d: %s",
                attempt,
                RETRIES,
                exc,
            )

        except Exception as exc:

            logger.exception(
                "Erro inesperado no download: %s",
                exc,
            )

        if attempt < RETRIES:

            wait_time = 2 ** (attempt - 1)

            logger.info(
                "Aguardando %d segundos para nova tentativa...",
                wait_time,
            )

            time.sleep(wait_time)

    try:

        if os.path.exists(temp_file):
            os.remove(temp_file)

    except OSError:
        pass

    logger.error(
        "Falha definitiva no download: %s",
        url,
    )

    return False


# ============================================================
# LISTA DE DOWNLOADS
# ============================================================

def get_download_lists():
    """Retorna as fontes de playlists e EPG."""

    return {
        "EPG": {
            "playlist": (
                "https://raw.githubusercontent.com/"
                "josieljefferson/EPG/refs/heads/main/"
                "output/playlist.m3u"
            ),
            "epg": (
                "https://raw.githubusercontent.com/"
                "josieljefferson/EPG/refs/heads/main/"
                "output/epg.xml.gz"
            ),
        },

        "EPG-M3U": {
            "playlist": (
                "https://raw.githubusercontent.com/"
                "josieljefferson/EPG-M3U/refs/heads/main/"
                "output/playlist.m3u"
            ),
            "epg": (
                "https://raw.githubusercontent.com/"
                "josieljefferson/EPG-M3U/refs/heads/main/"
                "output/epg.xml.gz"
            ),
        },
    }


# ============================================================
# CONSTRUÇÃO DAS TAREFAS
# ============================================================

def build_download_tasks():
    """
    Cria todas as tarefas de download.

    Cada playlist é salva em:

        playlists/
        iMPlayer/
        raiz/

    Cada EPG é salvo em:

        epg/
        iMPlayer/
    """

    sources = get_download_lists()

    tasks = []

    for source_name, files in sources.items():

        playlist_url = files["playlist"]
        epg_url = files["epg"]

        # ----------------------------------------------------
        # NOMES DOS ARQUIVOS
        # ----------------------------------------------------

        if source_name == "EPG":

            playlist_name = "playlist.m3u"
            epg_name = "playlist.xml.gz"

        else:

            playlist_name = "playlists.m3u"
            epg_name = "playlists.xml.gz"

        # ----------------------------------------------------
        # PLAYLIST -> playlists/
        # ----------------------------------------------------

        tasks.append(
            (
                playlist_url,
                os.path.join(
                    OUTPUT_DIRS["playlists"],
                    playlist_name,
                ),
            )
        )

        # ----------------------------------------------------
        # PLAYLIST -> iMPlayer/
        # ----------------------------------------------------

        tasks.append(
            (
                playlist_url,
                os.path.join(
                    OUTPUT_DIRS["implayer"],
                    playlist_name,
                ),
            )
        )

        # ----------------------------------------------------
        # PLAYLIST -> RAIZ
        # ----------------------------------------------------

        tasks.append(
            (
                playlist_url,
                os.path.join(
                    OUTPUT_DIRS["root"],
                    playlist_name,
                ),
            )
        )

        # ----------------------------------------------------
        # EPG -> epg/
        # ----------------------------------------------------

        tasks.append(
            (
                epg_url,
                os.path.join(
                    OUTPUT_DIRS["epg"],
                    epg_name,
                ),
            )
        )

        # ----------------------------------------------------
        # EPG -> iMPlayer/
        # ----------------------------------------------------

        tasks.append(
            (
                epg_url,
                os.path.join(
                    OUTPUT_DIRS["implayer"],
                    epg_name,
                ),
            )
        )

    return tasks


# ============================================================
# PREPARAÇÃO DOS DIRETÓRIOS
# ============================================================

def prepare_directories():
    """Prepara os diretórios necessários."""

    success = True

    for directory in OUTPUT_DIRS.values():

        if not create_directory(directory):
            success = False

    return success


# ============================================================
# DOWNLOAD DE UMA TAREFA
# ============================================================

def process_task(task):
    """Processa uma única tarefa."""

    url, destination = task

    result = download_file(
        url,
        destination,
    )

    return (
        url,
        destination,
        result,
    )


# ============================================================
# MAIN
# ============================================================

def main():
    """Função principal."""

    logger.info("=" * 70)
    logger.info(
        "📥 INICIANDO MEDIA DOWNLOADER"
    )
    logger.info("=" * 70)

    start_time = time.time()

    clean_temp_files()

    if not prepare_directories():

        logger.error(
            "Não foi possível preparar os diretórios."
        )

        return 1

    tasks = build_download_tasks()

    logger.info(
        "Total de tarefas de download: %d",
        len(tasks),
    )

    successful = 0
    failed = 0

    # --------------------------------------------------------
    # EXECUÇÃO PARALELA
    # --------------------------------------------------------

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        future_map = {
            executor.submit(
                process_task,
                task,
            ): task
            for task in tasks
        }

        for future in as_completed(
            future_map
        ):

            task = future_map[future]

            try:

                url, destination, result = (
                    future.result()
                )

                if result:

                    successful += 1

                    logger.info(
                        "✅ OK: %s",
                        destination,
                    )

                else:

                    failed += 1

                    logger.error(
                        "❌ FALHA: %s",
                        destination,
                    )

            except Exception as exc:

                failed += 1

                logger.exception(
                    "Erro processando tarefa %s: %s",
                    task,
                    exc,
                )

    # --------------------------------------------------------
    # LIMPEZA
    # --------------------------------------------------------

    clean_temp_files()

    elapsed = time.time() - start_time

    logger.info("=" * 70)
    logger.info(
        "📊 RESULTADO FINAL"
    )
    logger.info(
        "Sucessos: %d",
        successful,
    )
    logger.info(
        "Falhas: %d",
        failed,
    )
    logger.info(
        "Total: %d",
        len(tasks),
    )
    logger.info(
        "Tempo: %.2f segundos",
        elapsed,
    )
    logger.info("=" * 70)

    # --------------------------------------------------------
    # RESULTADO
    # --------------------------------------------------------

    if successful == 0:

        logger.error(
            "Nenhum arquivo foi baixado com sucesso."
        )

        return 1

    if failed > 0:

        logger.warning(
            "Existem %d tarefa(s) com falha.",
            failed,
        )

    else:

        logger.info(
            "🎉 Todos os downloads foram concluídos."
        )

    return 0


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":

    raise SystemExit(
        main()
    )
