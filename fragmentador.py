import hashlib
import json
import math
from pathlib import Path

dm_buffer_size = 1024 * 1024

def dm_calcular_hash(dm_caminho):
    dm_sha256 = hashlib.sha256()
    with open(dm_caminho, "rb") as dm_arquivo:
        while dm_bloco := dm_arquivo.read(dm_buffer_size):
            dm_sha256.update(dm_bloco)
    return dm_sha256.hexdigest()

def dm_dividir_arquivo():
    dm_entrada = input("Informe o arquivo para fragmentar: ").strip('\"\'')
    dm_caminho_arquivo = Path(dm_entrada)
    
    if not dm_caminho_arquivo.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {dm_caminho_arquivo}")
    
    dm_quantidade_partes = 4
    dm_tamanho_total = dm_caminho_arquivo.stat().st_size
    
    if dm_tamanho_total < dm_quantidade_partes:
        raise ValueError("Arquivo menor que a quantidade de partes solicitada.")
        
    dm_tamanho_parte = math.ceil(dm_tamanho_total / dm_quantidade_partes)
    dm_hash_original = dm_calcular_hash(dm_caminho_arquivo)
    
    dm_manifest = {
        "versao_manifesto": 2,
        "arquivo_original": dm_caminho_arquivo.name,
        "tamanho_original_bytes": dm_tamanho_total,
        "sha256_original": dm_hash_original,
        "quantidade_partes_esperada": dm_quantidade_partes,
        "limite_bytes_por_parte": dm_tamanho_parte,
        "partes": []
    }
    
    print(f"\nTamanho total original: {dm_tamanho_total} bytes")
    
    with open(dm_caminho_arquivo, "rb") as dm_arquivo_original:
        for dm_numero in range(1, dm_quantidade_partes + 1):
            dm_nome_parte = f"{dm_caminho_arquivo.name}.part{dm_numero:03d}"
            dm_caminho_parte = dm_caminho_arquivo.parent / dm_nome_parte
            dm_bytes_escritos = 0
            
            with open(dm_caminho_parte, "wb") as dm_arquivo_parte:
                while dm_bytes_escritos < dm_tamanho_parte:
                    dm_tamanho_leitura = min(dm_buffer_size, dm_tamanho_parte - dm_bytes_escritos)
                    dm_bloco = dm_arquivo_original.read(dm_tamanho_leitura)
                    if not dm_bloco:
                        break
                    dm_arquivo_parte.write(dm_bloco)
                    dm_bytes_escritos += len(dm_bloco)
            
            dm_hash_parte = dm_calcular_hash(dm_caminho_parte)
            dm_manifest["partes"].append({
                "numero": dm_numero,
                "arquivo": dm_nome_parte,
                "tamanho_bytes": dm_bytes_escritos,
                "sha256": dm_hash_parte
            })
            print(f"Gerado: {dm_nome_parte} | Tamanho: {dm_bytes_escritos} bytes")
    
    dm_caminho_manifest = dm_caminho_arquivo.parent / f"{dm_caminho_arquivo.name}.manifest.json"
    with open(dm_caminho_manifest, "w", encoding="utf-8") as dm_arquivo_manifest:
        json.dump(dm_manifest, dm_arquivo_manifest, indent=4, ensure_ascii=False)
    
    print(f"\nManifesto de controle estruturado e gerado: {dm_caminho_manifest.name}")

def dm_reconstruir_arquivo():
    dm_entrada = input("Informe o arquivo manifest.json para reconstruir: ").strip('\"\'')
    dm_caminho_manifest = Path(dm_entrada)
    
    if not dm_caminho_manifest.is_file():
        raise FileNotFoundError(f"Manifesto não encontrado: {dm_caminho_manifest}")
    
    with open(dm_caminho_manifest, "r", encoding="utf-8") as dm_arquivo:
        dm_manifest = json.load(dm_arquivo)
        
    if dm_manifest.get("versao_manifesto") != 2:
        raise ValueError("Versão do manifesto incompatível.")
    
    dm_diretorio = dm_caminho_manifest.parent
    dm_nome_original = dm_manifest["arquivo_original"]
    dm_caminho_saida = dm_diretorio / f"reconstruido_{dm_nome_original}"
    
    if dm_caminho_saida.exists():
        raise FileExistsError(f"O arquivo reconstruído já existe: {dm_caminho_saida}")
        
    dm_partes = sorted(dm_manifest["partes"], key=lambda dm_item: dm_item["numero"])
    
    if len(dm_partes) != dm_manifest.get("quantidade_partes_esperada"):
        raise ValueError("A quantidade de partes no manifesto é diferente da quantidade esperada.")
        
    dm_numeros_encontrados = [dm_parte["numero"] for dm_parte in dm_partes]
    dm_numeros_esperados = list(range(1, dm_manifest.get("quantidade_partes_esperada") + 1))
    
    if dm_numeros_encontrados != dm_numeros_esperados:
        raise ValueError("A numeração das partes está incompleta, duplicada ou fora de ordem.")
    
    print("\nExecutando auditoria rigorosa das partes antes da fusão...")
    for dm_parte in dm_partes:
        dm_caminho_parte = dm_diretorio / dm_parte["arquivo"]
        if not dm_caminho_parte.is_file():
            raise FileNotFoundError(f"Falha Crítica: Parte ausente: {dm_parte['arquivo']}")
        
        if dm_caminho_parte.stat().st_size != dm_parte["tamanho_bytes"]:
            raise ValueError(f"Falha Crítica: Divergência de tamanho detectada na parte: {dm_parte['arquivo']}")
            
        if dm_calcular_hash(dm_caminho_parte) != dm_parte["sha256"]:
            raise ValueError(f"Falha Crítica: Corrompimento de hash detectado na parte: {dm_parte['arquivo']}")
            
        print(f"Íntegro: {dm_parte['arquivo']}")
    
    print(f"\nIniciando gravação do arquivo finalizado...")
    with open(dm_caminho_saida, "wb") as dm_arquivo_reconstruido:
        for dm_parte in dm_partes:
            dm_caminho_parte = dm_diretorio / dm_parte["arquivo"]
            with open(dm_caminho_parte, "rb") as dm_arquivo_parte:
                while dm_bloco := dm_arquivo_parte.read(dm_buffer_size):
                    dm_arquivo_reconstruido.write(dm_bloco)
    
    dm_tamanho_reconstruido = dm_caminho_saida.stat().st_size
    if dm_tamanho_reconstruido != dm_manifest["tamanho_original_bytes"]:
        dm_caminho_saida.unlink(missing_ok=True)
        raise ValueError("Reversão Aplicada: O tamanho do arquivo final construído diverge do manifesto original.")
        
    if dm_calcular_hash(dm_caminho_saida) != dm_manifest["sha256_original"]:
        dm_caminho_saida.unlink(missing_ok=True)
        raise ValueError("Reversão Aplicada: O hash do arquivo final construído diverge do manifesto original.")
        
    print(f"\nSucesso: Arquivo validado contra a assinatura original e salvo em: {dm_caminho_saida}")

def dm_main():
    print("SISTEMA DE FRAGMENTAÇÃO SHA-256")
    dm_escolha = input("Digite 1 para Fragmentar ou 2 para Reconstruir: ").strip()
    if dm_escolha == "1":
        dm_dividir_arquivo()
    elif dm_escolha == "2":
        dm_reconstruir_arquivo()
    else:
        print("Comando abortado. Opção inválida.")

if __name__ == "__main__":
    dm_main()