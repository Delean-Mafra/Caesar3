import hashlib
import json
import re
from pathlib import Path
from tkinter import Tk, filedialog


# Cada fragmento terá, no máximo, 24 MiB.
DM_TAMANHO_FRAGMENTO = 24 * 1024 * 1024

# Somente arquivos maiores que 25 MiB serão fragmentados.
DM_TAMANHO_MINIMO = 25 * 1024 * 1024

# Leitura e escrita em blocos de 1 MiB.
DM_BUFFER_SIZE = 1024 * 1024

DM_VERSAO_MANIFESTO = 4
DM_NOME_MANIFESTO = "manifest.json"


def dm_selecionar_pasta(dm_titulo):
    """Abre a janela do Windows para seleção de uma pasta."""
    dm_janela = Tk()
    dm_janela.withdraw()
    dm_janela.attributes("-topmost", True)

    try:
        dm_pasta = filedialog.askdirectory(title=dm_titulo)
    finally:
        dm_janela.destroy()

    if not dm_pasta:
        return None

    return Path(dm_pasta).resolve()


def dm_calcular_hash(dm_caminho):
    """Calcula o SHA-256 de um arquivo."""
    dm_sha256 = hashlib.sha256()

    with open(dm_caminho, "rb") as dm_arquivo:
        while True:
            dm_bloco = dm_arquivo.read(DM_BUFFER_SIZE)

            if not dm_bloco:
                break

            dm_sha256.update(dm_bloco)

    return dm_sha256.hexdigest()


def dm_formatar_tamanho(dm_bytes):
    """Converte bytes para uma representação legível."""
    return f"{dm_bytes / (1024 * 1024):.2f} MiB"


def dm_sanitizar_nome(dm_texto):
    """
    Prepara o nome para uso como pasta no Windows.

    Caracteres inválidos:
    < > : " / \\ | ? *
    """
    dm_texto = re.sub(r'[<>:"/\\|?*]', "_", dm_texto)
    dm_texto = dm_texto.rstrip(" .")

    if not dm_texto:
        return "arquivo"

    return dm_texto


def dm_obter_nome_pasta_fragmentos(dm_caminho_arquivo):
    """
    Gera o nome da subpasta usando nome e extensão.

    Caesar3.img -> Caesar3_img
    Caesar3.iso -> Caesar3_iso
    arquivo.tar.gz -> arquivo_tar_gz
    """
    dm_nome_completo = dm_caminho_arquivo.name

    if "." in dm_nome_completo:
        dm_nome_pasta = dm_nome_completo.replace(".", "_")
    else:
        dm_nome_pasta = f"{dm_nome_completo}_sem_extensao"

    return dm_sanitizar_nome(dm_nome_pasta)


def dm_arquivo_esta_dentro_de_pasta_fragmentada(dm_caminho):
    """
    Verifica se o arquivo está dentro de uma pasta que já contém manifesto.

    Isso evita que os próprios fragmentos sejam fragmentados novamente.
    """
    dm_pasta_atual = dm_caminho.parent

    while True:
        if (dm_pasta_atual / DM_NOME_MANIFESTO).is_file():
            return True

        dm_pasta_pai = dm_pasta_atual.parent

        if dm_pasta_pai == dm_pasta_atual:
            break

        dm_pasta_atual = dm_pasta_pai

    return False


def dm_listar_arquivos_para_fragmentar(
    dm_pasta,
    dm_incluir_subpastas=False
):
    """
    Lista arquivos maiores que 25 MiB.

    Por padrão, considera somente arquivos diretamente dentro da pasta
    selecionada. Subpastas podem ser incluídas por parâmetro.
    """
    if dm_incluir_subpastas:
        dm_candidatos = dm_pasta.rglob("*")
    else:
        dm_candidatos = dm_pasta.iterdir()

    dm_arquivos = []

    for dm_caminho in dm_candidatos:
        if not dm_caminho.is_file():
            continue

        if dm_caminho.name == DM_NOME_MANIFESTO:
            continue

        if ".part" in dm_caminho.suffix.lower():
            continue

        if dm_arquivo_esta_dentro_de_pasta_fragmentada(dm_caminho):
            continue

        try:
            dm_tamanho = dm_caminho.stat().st_size
        except OSError:
            continue

        if dm_tamanho > DM_TAMANHO_MINIMO:
            dm_arquivos.append(dm_caminho)

    return sorted(
        dm_arquivos,
        key=lambda dm_item: str(dm_item).lower()
    )


def dm_fragmentar_um_arquivo(dm_caminho_arquivo):
    """Fragmenta um arquivo dentro de uma subpasta própria."""
    dm_tamanho_total = dm_caminho_arquivo.stat().st_size

    if dm_tamanho_total <= DM_TAMANHO_MINIMO:
        print(
            f"Ignorado: {dm_caminho_arquivo.name} | "
            f"{dm_formatar_tamanho(dm_tamanho_total)}"
        )
        return False

    dm_nome_pasta = dm_obter_nome_pasta_fragmentos(
        dm_caminho_arquivo
    )

    dm_pasta_fragmentos = (
        dm_caminho_arquivo.parent / dm_nome_pasta
    )

    if dm_pasta_fragmentos.exists():
        raise FileExistsError(
            "A pasta de fragmentos já existe:\n"
            f"{dm_pasta_fragmentos}"
        )

    dm_quantidade_partes = (
        dm_tamanho_total + DM_TAMANHO_FRAGMENTO - 1
    ) // DM_TAMANHO_FRAGMENTO

    print("\n" + "=" * 70)
    print(f"ARQUIVO: {dm_caminho_arquivo}")
    print(f"TAMANHO: {dm_formatar_tamanho(dm_tamanho_total)}")
    print(f"DESTINO: {dm_pasta_fragmentos}")
    print(f"PARTES: {dm_quantidade_partes}")
    print("=" * 70)

    print("Calculando SHA-256 do arquivo original...")
    dm_hash_original = dm_calcular_hash(dm_caminho_arquivo)

    dm_manifesto = {
        "versao_manifesto": DM_VERSAO_MANIFESTO,
        "arquivo_original": dm_caminho_arquivo.name,
        "caminho_relativo_original": dm_caminho_arquivo.name,
        "tamanho_original_bytes": dm_tamanho_total,
        "sha256_original": dm_hash_original,
        "tamanho_maximo_parte_bytes": DM_TAMANHO_FRAGMENTO,
        "tamanho_minimo_fragmentacao_bytes": DM_TAMANHO_MINIMO,
        "quantidade_partes_esperada": dm_quantidade_partes,
        "partes": []
    }

    dm_pasta_fragmentos.mkdir(parents=False, exist_ok=False)

    dm_partes_criadas = []
    dm_caminho_manifesto = (
        dm_pasta_fragmentos / DM_NOME_MANIFESTO
    )

    try:
        with open(dm_caminho_arquivo, "rb") as dm_arquivo_original:
            for dm_numero in range(1, dm_quantidade_partes + 1):
                dm_nome_parte = (
                    f"{dm_caminho_arquivo.name}.part"
                    f"{dm_numero:04d}"
                )

                dm_caminho_parte = (
                    dm_pasta_fragmentos / dm_nome_parte
                )

                dm_bytes_escritos = 0

                with open(dm_caminho_parte, "wb") as dm_arquivo_parte:
                    while dm_bytes_escritos < DM_TAMANHO_FRAGMENTO:
                        dm_bytes_restantes = (
                            DM_TAMANHO_FRAGMENTO
                            - dm_bytes_escritos
                        )

                        dm_tamanho_leitura = min(
                            DM_BUFFER_SIZE,
                            dm_bytes_restantes
                        )

                        dm_bloco = dm_arquivo_original.read(
                            dm_tamanho_leitura
                        )

                        if not dm_bloco:
                            break

                        dm_arquivo_parte.write(dm_bloco)
                        dm_bytes_escritos += len(dm_bloco)

                dm_partes_criadas.append(dm_caminho_parte)
                dm_hash_parte = dm_calcular_hash(
                    dm_caminho_parte
                )

                dm_manifesto["partes"].append({
                    "numero": dm_numero,
                    "arquivo": dm_nome_parte,
                    "tamanho_bytes": dm_bytes_escritos,
                    "sha256": dm_hash_parte
                })

                print(
                    f"[{dm_numero}/{dm_quantidade_partes}] "
                    f"{dm_nome_parte} | "
                    f"{dm_formatar_tamanho(dm_bytes_escritos)}"
                )

        with open(
            dm_caminho_manifesto,
            "w",
            encoding="utf-8"
        ) as dm_arquivo_manifesto:
            json.dump(
                dm_manifesto,
                dm_arquivo_manifesto,
                indent=4,
                ensure_ascii=False
            )

    except Exception:
        print(
            "\nA fragmentação falhou. "
            "Removendo arquivos incompletos..."
        )

        dm_caminho_manifesto.unlink(missing_ok=True)

        for dm_parte_criada in dm_partes_criadas:
            dm_parte_criada.unlink(missing_ok=True)

        try:
            dm_pasta_fragmentos.rmdir()
        except OSError:
            pass

        raise

    print("\nFRAGMENTAÇÃO CONCLUÍDA")
    print(f"Pasta: {dm_pasta_fragmentos}")
    print(f"Manifesto: {dm_caminho_manifesto}")
    print(f"SHA-256 original: {dm_hash_original}")

    return True


def dm_fragmentar_pasta():
    """
    Solicita uma pasta e fragmenta os arquivos maiores que 25 MiB
    encontrados diretamente dentro dela.
    """
    dm_pasta = dm_selecionar_pasta(
        "Selecione a pasta que contém os arquivos"
    )

    if dm_pasta is None:
        print("Seleção cancelada.")
        return

    if not dm_pasta.is_dir():
        raise NotADirectoryError(
            f"Pasta inválida: {dm_pasta}"
        )

    print(f"\nPasta selecionada: {dm_pasta}")
    print(
        "Procurando arquivos maiores que "
        f"{dm_formatar_tamanho(DM_TAMANHO_MINIMO)}..."
    )

    dm_arquivos = dm_listar_arquivos_para_fragmentar(
        dm_pasta,
        dm_incluir_subpastas=False
    )

    if not dm_arquivos:
        print(
            "\nNenhum arquivo maior que 25 MiB foi encontrado "
            "diretamente na pasta selecionada."
        )
        return

    print(f"\nArquivos que serão fragmentados: {len(dm_arquivos)}")

    for dm_indice, dm_arquivo in enumerate(
        dm_arquivos,
        start=1
    ):
        print(
            f"{dm_indice}. {dm_arquivo.name} | "
            f"{dm_formatar_tamanho(dm_arquivo.stat().st_size)}"
        )

    dm_sucessos = 0
    dm_falhas = 0

    for dm_indice, dm_arquivo in enumerate(
        dm_arquivos,
        start=1
    ):
        print(
            f"\nProcessando arquivo "
            f"{dm_indice} de {len(dm_arquivos)}..."
        )

        try:
            if dm_fragmentar_um_arquivo(dm_arquivo):
                dm_sucessos += 1
        except Exception as dm_erro:
            dm_falhas += 1
            print(f"\nERRO: {dm_erro}")

    print("\n" + "=" * 70)
    print("PROCESSAMENTO DA PASTA CONCLUÍDO")
    print(f"Arquivos fragmentados: {dm_sucessos}")
    print(f"Arquivos com erro: {dm_falhas}")
    print("=" * 70)


def dm_validar_manifesto(dm_manifesto):
    """Valida a estrutura básica do manifesto."""
    dm_campos_obrigatorios = [
        "versao_manifesto",
        "arquivo_original",
        "tamanho_original_bytes",
        "sha256_original",
        "quantidade_partes_esperada",
        "partes"
    ]

    for dm_campo in dm_campos_obrigatorios:
        if dm_campo not in dm_manifesto:
            raise ValueError(
                "Campo obrigatório ausente no manifesto: "
                f"{dm_campo}"
            )

    if dm_manifesto["versao_manifesto"] != DM_VERSAO_MANIFESTO:
        raise ValueError(
            "A versão do manifesto não é compatível "
            "com este programa."
        )

    dm_quantidade_esperada = dm_manifesto[
        "quantidade_partes_esperada"
    ]

    dm_partes = dm_manifesto["partes"]

    if not isinstance(dm_partes, list):
        raise ValueError(
            "O campo 'partes' do manifesto é inválido."
        )

    if len(dm_partes) != dm_quantidade_esperada:
        raise ValueError(
            "A quantidade de partes presentes no manifesto "
            "está incorreta."
        )

    dm_numeros_encontrados = sorted(
        dm_parte["numero"] for dm_parte in dm_partes
    )

    dm_numeros_esperados = list(
        range(1, dm_quantidade_esperada + 1)
    )

    if dm_numeros_encontrados != dm_numeros_esperados:
        raise ValueError(
            "A numeração das partes está incompleta "
            "ou duplicada."
        )


def dm_reconstruir_por_manifesto(
    dm_caminho_manifesto,
    dm_pasta_saida
):
    """Reconstrói um arquivo usando um manifesto."""
    with open(
        dm_caminho_manifesto,
        "r",
        encoding="utf-8"
    ) as dm_arquivo:
        dm_manifesto = json.load(dm_arquivo)

    dm_validar_manifesto(dm_manifesto)

    dm_diretorio_fragmentos = dm_caminho_manifesto.parent
    dm_nome_original = dm_manifesto["arquivo_original"]

    dm_caminho_saida = dm_pasta_saida / dm_nome_original
    dm_caminho_temporario = (
        dm_pasta_saida / f"{dm_nome_original}.reconstruindo.tmp"
    )

    if dm_caminho_saida.exists():
        raise FileExistsError(
            f"O arquivo de saída já existe: {dm_caminho_saida}"
        )

    dm_pasta_saida.mkdir(parents=True, exist_ok=True)
    dm_caminho_temporario.unlink(missing_ok=True)

    dm_partes = sorted(
        dm_manifesto["partes"],
        key=lambda dm_item: dm_item["numero"]
    )

    print("\n" + "=" * 70)
    print(f"MANIFESTO: {dm_caminho_manifesto}")
    print(f"ARQUIVO: {dm_nome_original}")
    print(f"SAÍDA: {dm_caminho_saida}")
    print("=" * 70)

    print("\nValidando os fragmentos...")

    for dm_indice, dm_parte in enumerate(
        dm_partes,
        start=1
    ):
        dm_caminho_parte = (
            dm_diretorio_fragmentos / dm_parte["arquivo"]
        )

        if not dm_caminho_parte.is_file():
            raise FileNotFoundError(
                f"Fragmento ausente: {dm_caminho_parte}"
            )

        dm_tamanho_atual = dm_caminho_parte.stat().st_size

        if dm_tamanho_atual != dm_parte["tamanho_bytes"]:
            raise ValueError(
                f"Tamanho incorreto: {dm_parte['arquivo']}"
            )

        dm_hash_atual = dm_calcular_hash(dm_caminho_parte)

        if dm_hash_atual != dm_parte["sha256"]:
            raise ValueError(
                f"Fragmento corrompido: {dm_parte['arquivo']}"
            )

        print(
            f"[{dm_indice}/{len(dm_partes)}] "
            f"Íntegro: {dm_parte['arquivo']}"
        )

    print("\nReconstruindo o arquivo...")

    try:
        with open(
            dm_caminho_temporario,
            "wb"
        ) as dm_arquivo_reconstruido:

            for dm_indice, dm_parte in enumerate(
                dm_partes,
                start=1
            ):
                dm_caminho_parte = (
                    dm_diretorio_fragmentos
                    / dm_parte["arquivo"]
                )

                with open(
                    dm_caminho_parte,
                    "rb"
                ) as dm_arquivo_parte:
                    while True:
                        dm_bloco = dm_arquivo_parte.read(
                            DM_BUFFER_SIZE
                        )

                        if not dm_bloco:
                            break

                        dm_arquivo_reconstruido.write(dm_bloco)

                print(
                    f"[{dm_indice}/{len(dm_partes)}] "
                    f"Adicionado: {dm_parte['arquivo']}"
                )

        dm_tamanho_reconstruido = (
            dm_caminho_temporario.stat().st_size
        )

        if (
            dm_tamanho_reconstruido
            != dm_manifesto["tamanho_original_bytes"]
        ):
            raise ValueError(
                "O tamanho do arquivo reconstruído "
                "diverge do original."
            )

        print("\nCalculando SHA-256 do arquivo reconstruído...")

        dm_hash_reconstruido = dm_calcular_hash(
            dm_caminho_temporario
        )

        if dm_hash_reconstruido != dm_manifesto["sha256_original"]:
            raise ValueError(
                "O SHA-256 do arquivo reconstruído "
                "diverge do original."
            )

        dm_caminho_temporario.replace(dm_caminho_saida)

    except Exception:
        dm_caminho_temporario.unlink(missing_ok=True)
        raise

    print("\nRECONSTRUÇÃO CONCLUÍDA")
    print(f"Arquivo: {dm_caminho_saida}")
    print(f"SHA-256: {dm_hash_reconstruido}")

    return True


def dm_reconstruir_pasta():
    """
    Seleciona a pasta que contém as subpastas de fragmentos,
    localiza os manifestos e reconstrói todos os arquivos.
    """
    dm_pasta_origem = dm_selecionar_pasta(
        "Selecione a pasta que contém os fragmentos"
    )

    if dm_pasta_origem is None:
        print("Seleção cancelada.")
        return

    dm_manifestos = sorted(
        dm_pasta_origem.rglob(DM_NOME_MANIFESTO),
        key=lambda dm_item: str(dm_item).lower()
    )

    if not dm_manifestos:
        print(
            "\nNenhum arquivo manifest.json foi encontrado em:\n"
            f"{dm_pasta_origem}"
        )
        return

    print(
        f"\nForam encontrados {len(dm_manifestos)} "
        "manifestos."
    )

    dm_pasta_saida = dm_selecionar_pasta(
        "Selecione a pasta onde os arquivos serão reconstruídos"
    )

    if dm_pasta_saida is None:
        print("Seleção da pasta de saída cancelada.")
        return

    print(f"\nOrigem: {dm_pasta_origem}")
    print(f"Saída: {dm_pasta_saida}")

    dm_sucessos = 0
    dm_falhas = 0

    for dm_indice, dm_manifesto in enumerate(
        dm_manifestos,
        start=1
    ):
        print(
            f"\nReconstruindo arquivo "
            f"{dm_indice} de {len(dm_manifestos)}..."
        )

        try:
            dm_reconstruir_por_manifesto(
                dm_manifesto,
                dm_pasta_saida
            )
            dm_sucessos += 1
        except Exception as dm_erro:
            dm_falhas += 1
            print(f"\nERRO: {dm_erro}")

    print("\n" + "=" * 70)
    print("PROCESSAMENTO DA RECONSTRUÇÃO CONCLUÍDO")
    print(f"Arquivos reconstruídos: {dm_sucessos}")
    print(f"Arquivos com erro: {dm_falhas}")
    print("=" * 70)


def dm_main():
    while True:
        print("\n" + "=" * 70)
        print("FRAGMENTADOR DE ARQUIVOS")
        print("=" * 70)
        print("Fragmentos: 24 MiB")
        print("Fragmentar somente arquivos maiores que 25 MiB")
        print()
        print("1 - Selecionar pasta e fragmentar arquivos")
        print("2 - Selecionar pasta e reconstruir arquivos")
        print("0 - Sair")

        dm_escolha = input("\nEscolha uma opção: ").strip()

        try:
            if dm_escolha == "1":
                dm_fragmentar_pasta()
            elif dm_escolha == "2":
                dm_reconstruir_pasta()
            elif dm_escolha == "0":
                print("Programa encerrado.")
                break
            else:
                print("Opção inválida.")
        except PermissionError as dm_erro:
            print(
                "\nERRO DE PERMISSÃO\n"
                "Verifique se o arquivo está aberto em outro programa "
                "ou execute o programa com as permissões necessárias.\n"
                f"Detalhes: {dm_erro}"
            )
        except Exception as dm_erro:
            print(f"\nERRO: {dm_erro}")

        input("\nPressione ENTER para voltar ao menu...")


if __name__ == "__main__":
    dm_main()
