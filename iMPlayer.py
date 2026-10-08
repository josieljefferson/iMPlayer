#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
=============================================================
                    iMPLAYER DOWNLOADER
=============================================================

Baixa playlists M3U e EPG XML.GZ de múltiplas fontes.

Arquivos gerados:

    iMPlayer/iMPlayer_1.m3u
    iMPlayer/iMPlayer_2.m3u

    iMPlayer/iMPlayer_1.xml.gz
    iMPlayer/iMPlayer_2.xml.gz

=============================================================
"""

import logging
import os
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
    )
}

OUTPUT_DIR = os.path.join(
    os.getcwd(),
    "iMPlayer"
)

TIMEOUT = 30

RETRIES = 3

MAX_WORKERS = 4


# =============================================================
# LOGGING
# =============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


# =============================================================
# FONTES DE DOWNLOAD
# =============================================================

FILES_TO_DOWNLOAD = {

    "m3u": [
        "https://raw.githubusercontent.com/"
        "josieljefferson/EPG/refs/heads/main/output/playlist.m3u",

        "https://raw.githubusercontent.com/"
        "josieljefferson/EPG-M3U/refs/heads/main/output/playlist.m3u",
    ],

    "xml.gz": [
        "https://raw.githubusercontent.com/"
        "josieljefferson/EPG/refs/heads/main/output/epg.xml.gz",

        "https://raw.githubusercontent.com/"
        "josieljefferson/EPG-M3U/refs/heads/main/output/epg.xml.gz",
    ],
}


# =============================================================
# DOWNLOAD DE ARQUIVO
# =============================================================

def download_file(url, save_path, retries=RETRIES):
    """
    Baixa um arquivo da URL informada.

    O download é feito inicialmente em um arquivo temporário.
    Somente após o download ser concluído com sucesso o arquivo
    temporário substitui o arquivo definitivo.

    Isso evita deixar arquivos parcialmente baixados.
    """

    directory = os.path.dirname(save_path)

    os.makedirs(
        directory,
        exist_ok=True
    )

    temp_path = save_path + ".tmp"

    for attempt in range(1, retries + 1):

        try:

            logger.info(
                "Tentativa %d/%d: %s",
                attempt,
                retries,
                url,
            )

            response = requests.get(
                url,
                headers=HEADERS,
                timeout=TIMEOUT,
            )

            response.raise_for_status()

            content = response.content

            if not content:
                raise ValueError(
                    "Servidor retornou conteúdo vazio."
                )

            # -------------------------------------------------
            # SALVAR TEMPORÁRIO
            # -------------------------------------------------

            with open(
                temp_path,
                "wb"
            ) as file:

                file.write(content)

            file_size = os.path.getsize(
                temp_path
            )

            if file_size <= 0:
                raise ValueError(
                    "Arquivo baixado está vazio."
                )

            # -------------------------------------------------
            # CALCULAR MD5
            # -------------------------------------------------

            with open(
                temp_path,
                "rb"
            ) as file:

                file_hash = md5(
                    file.read()
                ).hexdigest()

            # -------------------------------------------------
            # SUBSTITUIR ARQUIVO DEFINITIVO
            # -------------------------------------------------

            os.replace(
                temp_path,
                save_path
            )

            logger.info(
                "Arquivo salvo com sucesso: %s",
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
                "Timeout ao baixar: %s",
                url,
            )

        except requests.exceptions.ConnectionError:

            logger.error(
                "Erro de conexão ao baixar: %s",
                url,
            )

        except requests.exceptions.HTTPError as error:

            logger.error(
                "Erro HTTP ao baixar %s: %s",
                url,
                error,
            )

        except Exception as error:

            logger.error(
                "Erro inesperado ao baixar %s: %s",
                url,
                error,
            )

        # -----------------------------------------------------
        # REMOVER TEMPORÁRIO
        # -----------------------------------------------------

        if os.path.exists(temp_path):

            try:
                os.remove(temp_path)

            except OSError:
                pass

    logger.error(
        "Falha definitiva após %d tentativas: %s",
        retries,
        url,
    )

    return False


# =============================================================
# PREPARAR DIRETÓRIO
# =============================================================

def prepare_output_directory():
    """
    Cria o diretório de saída caso ele não exista.

    Arquivos temporários de execuções anteriores são removidos.

    Os arquivos definitivos existentes são preservados até que
    um novo download seja concluído com sucesso.
    """

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    for filename in os.listdir(
        OUTPUT_DIR
    ):

        if not filename.endswith(
            ".tmp"
        ):
            continue

        path = os.path.join(
            OUTPUT_DIR,
            filename
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
# CRIAR LISTA DE TAREFAS
# =============================================================

def build_download_tasks():
    """
    Cria a lista de downloads.

    Retorna:

        [
            (url, caminho_destino),
            ...
        ]
    """

    tasks = []

    for extension, urls in FILES_TO_DOWNLOAD.items():

        for index, url in enumerate(
            urls,
            start=1
        ):

            filename = (
                f"iMPlayer_{index}.{extension}"
            )

            save_path = os.path.join(
                OUTPUT_DIR,
                filename
            )

            tasks.append(
                (
                    url,
                    save_path
                )
            )

    return tasks


# =============================================================
# PRINCIPAL
# =============================================================

def main():

    logger.info("=" * 60)

    logger.info(
        "INICIANDO DOWNLOAD DO iMPLAYER"
    )

    logger.info("=" * 60)

    # ---------------------------------------------------------
    # PREPARAR DIRETÓRIO
    # ---------------------------------------------------------

    prepare_output_directory()

    # ---------------------------------------------------------
    # CRIAR TAREFAS
    # ---------------------------------------------------------

    tasks = build_download_tasks()

    logger.info(
        "Total de arquivos para baixar: %d",
        len(tasks),
    )

    # ---------------------------------------------------------
    # DOWNLOAD PARALELO
    # ---------------------------------------------------------

    success_count = 0

    failure_count = 0

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = {
            executor.submit(
                download_file,
                url,
                save_path,
            ): (
                url,
                save_path,
            )

            for url, save_path in tasks
        }

        for future in as_completed(
            futures
        ):

            url, save_path = futures[
                future
            ]

            try:

                success = future.result()

                if success:

                    success_count += 1

                else:

                    failure_count += 1

            except Exception as error:

                failure_count += 1

                logger.error(
                    "Erro inesperado em %s: %s",
                    save_path,
                    error,
                )

    # ---------------------------------------------------------
    # RESULTADO
    # ---------------------------------------------------------

    logger.info("=" * 60)

    logger.info(
        "DOWNLOAD CONCLUÍDO"
    )

    logger.info(
        "Sucessos: %d",
        success_count,
    )

    logger.info(
        "Falhas: %d",
        failure_count,
    )

    logger.info("=" * 60)

    # ---------------------------------------------------------
    # LISTAR ARQUIVOS
    # ---------------------------------------------------------

    if os.path.isdir(
        OUTPUT_DIR
    ):

        logger.info(
            "Arquivos disponíveis:"
        )

        for filename in sorted(
            os.listdir(OUTPUT_DIR)
        ):

            path = os.path.join(
                OUTPUT_DIR,
                filename
            )

            if not os.path.isfile(
                path
            ):
                continue

            logger.info(
                "  %s (%d bytes)",
                filename,
                os.path.getsize(path),
            )

    # ---------------------------------------------------------
    # FALHAR SE NENHUM DOWNLOAD FUNCIONAR
    # ---------------------------------------------------------

    if success_count == 0:

        logger.error(
            "Nenhum arquivo foi baixado com sucesso."
        )

        raise SystemExit(1)

    # ---------------------------------------------------------
    # AVISO DE DOWNLOAD PARCIAL
    # ---------------------------------------------------------

    if failure_count > 0:

        logger.warning(
            "%d arquivo(s) não foram baixados.",
            failure_count,
        )


# =============================================================
# EXECUÇÃO
# =============================================================

if __name__ == "__main__":
    main()
