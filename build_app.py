import os
import sys
import shutil
import subprocess
import site
import glob

def find_customtkinter_path():
    # Obtém os diretórios de pacotes do Python
    site_packages = site.getsitepackages()
    
    # Procura o diretório customtkinter
    customtkinter_path = None
    for path in site_packages:
        ctk_path = os.path.join(path, 'customtkinter')
        if os.path.exists(ctk_path):
            customtkinter_path = ctk_path
            break
    
    if not customtkinter_path:
        print("Erro: Não foi possível encontrar o pacote customtkinter.")
        sys.exit(1)
    
    return customtkinter_path

def update_spec_file(ctk_path):
    # Atualiza o arquivo .spec com o caminho correto para customtkinter
    with open('afk.spec', 'r') as file:
        content = file.read()
    
    # Modifica a linha de datas para incluir customtkinter
    if "datas=[]" in content:
        content = content.replace(
            "datas=[]", 
            f"datas=[(\"{ctk_path.replace('\\', '\\\\')}\", 'customtkinter/')]"
        )
        
        with open('afk.spec', 'w') as file:
            file.write(content)
        
        print(f"Arquivo afk.spec atualizado com o caminho: {ctk_path}")
    else:
        print("Aviso: Não foi possível atualizar o arquivo spec. A linha 'datas=[]' não foi encontrada.")

def build_executable():
    # Executa o PyInstaller
    cmd = ["pyinstaller", "--noconfirm", "afk.spec"]
    
    try:
        subprocess.run(cmd, check=True)
        print("\nExecutável criado com sucesso!")
        print("\nVocê pode encontrar o arquivo executável na pasta dist/")
    except subprocess.CalledProcessError:
        print("\nErro ao criar o executável.")
        sys.exit(1)

def main():
    print("Iniciando a criação do executável...\n")
    
    # Encontra o caminho do customtkinter
    ctk_path = find_customtkinter_path()
    print(f"CustomTkinter encontrado em: {ctk_path}")
    
    # Atualiza o arquivo .spec
    update_spec_file(ctk_path)
    
    # Cria o executável
    build_executable()

if __name__ == "__main__":
    main() 