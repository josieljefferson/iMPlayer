#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Baixador automático de playlists e EPG.

Arquivos gerados:
    playlists/EPG-playlist.m3u
    playlists/EPG-M3U-playlist.m3u
    playlists/EPG-epg.xml.gz
    playlists/EPG-M3U-epg.xml.gz

Características:
    - Downloads paralelos.
    - Até 3 tentativas por arquivo.
    - Timeout de 10 segundos.
    - Validação dos arquivos baixados.
    - Substituição dos arquivos somente após todos
      os downloads serem concluídos com sucesso.
    - Preserva os arquivos anteriores em caso de falha.
    - Retorna código de erro para o GitHub Actions.
"""

import os
import shutil
import tempfile
import logging
import requests

from hashlib import md5
from concurrent.futures import ThreadPoolExecutor, as_completed


# --------------------------------------------------
# CONFIGURAÇÕES
# --------------------------------------------------

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

BASE_DIR = os.getcwd()
OUTPUT_DIR = os.path.join(BASE_DIR, "playlists")

TIMEOUT = 10
RETRIES = 3
MAX_WORKERS = 5


# --------------------------------------------------
# LOGGING
# --------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# --------------------------------------------------
# VALIDAR URL
# --------------------------------------------------

def validate_url(url):
    """Valida o formato básico da URL."""

    if not isinstance(url, str):
        logger.error("URL inválida: o valor não é texto.")
        return False

    if not url.startswith(("https://", "http://")):
        logger.error("URL inválida: %s", url)
        return False

    return True


# --------------------------------------------------
# DOWNLOAD
# --------------------------------------------------

def download_file(url, save_path, retries=RETRIES):
    """
    Baixa um arquivo para o caminho informado.

    Retorna True em caso de sucesso e False em caso
    de falha após todas as tentativas.
    """

    if not validate_url(url):
        return False

    for attempt in range(1, retries + 1):
        temp_path = save_path + ".part"

        try:
            logger.info(
                "Tentativa %s/%s: %s",
                attempt,
                retries,
                url
            )

            with requests.get(
                url,
                headers=HEADERS,
                timeout=TIMEOUT,
                stream=True,
                allow_redirects=True
            ) as response:

                response.raise_for_status()

                os.makedirs(
                    os.path.dirname(save_path),
                    exist_ok=True
                )

                digest = md5()
                total_bytes = 0

                with open(temp_path, "wb") as file:
                    for chunk in response.iter_content(
                        chunk_size=64 * 1024
                    ):
                        if not chunk:
                            continue

                        file.write(chunk)
                        digest.update(chunk)
                        total_bytes += len(chunk)

                if total_bytes == 0:
                    raise ValueError(
                        "O servidor retornou um arquivo vazio."
                    )

                # Substitui o arquivo de destino de forma
                # atômica, após terminar a gravação.
                os.replace(temp_path, save_path)

                logger.info(
                    "Download concluído: %s (%s bytes)",
                    os.path.basename(save_path),
                    total_bytes
                )

                logger.info(
                    "MD5: %s",
                    digest.hexdigest()
                )

                return True

        except requests.exceptions.Timeout:
            logger.warning(
                "Timeout na tentativa %s/%s: %s",
                attempt,
                retries,
                url
            )

        except requests.exceptions.HTTPError as exc:
            logger.warning(
                "Erro HTTP na tentativa %s/%s: %s",
                attempt,
                retries,
                exc
            )

        except requests.exceptions.ConnectionError as exc:
            logger.warning(
                "Erro de conexão na tentativa %s/%s: %s",
                attempt,
                retries,
                exc
            )

        except requests.exceptions.RequestException as exc:
            logger.warning(
                "Erro na requisição: %s",
                exc
            )

        except (OSError, ValueError) as exc:
            logger.warning(
                "Erro ao gravar ou validar o arquivo: %s",
                exc
            )

        except Exception:
            logger.exception(
                "Erro inesperado durante o download: %s",
                url
            )

        finally:
            # Remove somente o arquivo parcial da tentativa.
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                logger.warning(
                    "Não foi possível remover: %s",
                    temp_path
                )

    logger.error(
        "Download falhou após %s tentativas: %s",
        retries,
        url
    )

    return False


# --------------------------------------------------
# LISTA DE ARQUIVOS
# --------------------------------------------------

def get_files_to_download():
    """Retorna os arquivos e as respectivas URLs."""

    return {
        "EPG-playlist.m3u":
            "https://raw.githubusercontent.com/"
            "josieljefferson/EPG/refs/heads/main/"
            "output/playlist.m3u",

        "EPG-M3U-playlist.m3u":
            "https://raw.githubusercontent.com/"
            "josieljefferson/EPG-M3U/refs/heads/main/"
            "output/playlist.m3u",

        "EPG-epg.xml.gz":
            "https://raw.githubusercontent.com/"
            "josieljefferson/EPG/refs/heads/main/"
            "output/epg.xml.gz",

        "EPG-M3U-epg.xml.gz":
            "https://raw.githubusercontent.com/"
            "josieljefferson/EPG-M3U/refs/heads/main/"
            "output/epg.xml.gz"
    }


# --------------------------------------------------
# EXECUÇÃO PRINCIPAL
# --------------------------------------------------

def main():
    logger.info("=" * 60)
    logger.info("INICIANDO DOWNLOAD DAS PLAYLISTS E EPG")
    logger.info("=" * 60)

    files_to_download = get_files_to_download()

    # A pasta temporária fica fora de playlists/.
    # Assim, downloads incompletos não apagam os arquivos
    # anteriormente publicados.
    staging_dir = tempfile.mkdtemp(
        prefix="playlists-download-"
    )

    results = {}

    try:
        with ThreadPoolExecutor(
            max_workers=MAX_WORKERS
        ) as executor:

            future_map = {
                executor.submit(
                    download_file,
                    url,
                    os.path.join(staging_dir, filename)
                ): (filename, url)
                for filename, url in files_to_download.items()
            }

            for future in as_completed(future_map):
                filename, url = future_map[future]

                try:
                    success = future.result()
                except Exception:
                    logger.exception(
                        "Falha inesperada em %s",
                        filename
                    )
                    success = False

                results[filename] = success

                if not success:
                    logger.error(
                        "Arquivo não baixado: %s (%s)",
                        filename,
                        url
                    )

        successful = sum(results.values())
        total = len(files_to_download)
        failed = total - successful

        logger.info(
            "Resultado: %s/%s downloads concluídos.",
            successful,
            total
        )

        if failed:
            logger.error(
                "%s download(s) falharam. "
                "Os arquivos anteriores serão preservados.",
                failed
            )

            raise RuntimeError(
                "Um ou mais downloads falharam."
            )

        # Confirma que todos os arquivos existem e não
        # estão vazios antes de publicar a nova pasta.
        for filename in files_to_download:
            file_path = os.path.join(
                staging_dir,
                filename
            )

            if not os.path.isfile(file_path):
                raise RuntimeError(
                    "Arquivo não encontrado: " + filename
                )

            if os.path.getsize(file_path) == 0:
                raise RuntimeError(
                    "Arquivo vazio: " + filename
                )

        # Todos os downloads foram validados.
        # Prepara a troca da pasta de saída.
        backup_dir = OUTPUT_DIR + ".backup"

        if os.path.exists(backup_dir):
            shutil.rmtree(backup_dir)

        had_previous_output = os.path.exists(OUTPUT_DIR)

        if had_previous_output:
            os.replace(OUTPUT_DIR, backup_dir)

        try:
            os.replace(staging_dir, OUTPUT_DIR)

        except Exception:
            # Se a publicação falhar, tenta restaurar
            # a pasta anterior.
            if (
                had_previous_output
                and os.path.exists(backup_dir)
                and not os.path.exists(OUTPUT_DIR)
            ):
                os.replace(backup_dir, OUTPUT_DIR)

            raise

        # A nova pasta foi publicada com sucesso.
        if os.path.exists(backup_dir):
            shutil.rmtree(backup_dir)

        logger.info("=" * 60)
        logger.info("DOWNLOADS CONCLUÍDOS COM SUCESSO")
        logger.info("Diretório: %s", OUTPUT_DIR)
        logger.info("Arquivos publicados: %s", total)
        logger.info("=" * 60)

    finally:
        # Remove os arquivos temporários restantes,
        # sem remover a pasta final de saída.
        if os.path.exists(staging_dir):
            shutil.rmtree(staging_dir, ignore_errors=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("A execução do playlists.py falhou.")
        raise
