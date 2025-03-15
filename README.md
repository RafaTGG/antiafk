# Monitor AFK

Um aplicativo para Windows que monitora a inatividade do sistema e desliga o computador automaticamente após um período configurável de tempo sem detecção de atividade.

## Funcionalidades

- Monitoramento automático de inatividade do teclado, mouse e joystick
- Configuração personalizada do tempo limite (em minutos)
- Interface gráfica moderna com tema escuro
- Suporte completo a joysticks (botões, eixos e direcionais)
- Opções para iniciar com o Windows
- Modo oculto na bandeja do sistema
- Atalho global (CTRL+SHIFT+A) para mostrar o aplicativo
- Aviso visual antes do desligamento
- Configurações salvas automaticamente

## Requisitos

- Windows
- Python 3.8 ou superior (para código fonte)
- Ou executável compilado (standalone)

## Instalação

### Usando o executável compilado

1. Baixe a versão mais recente na seção de [Releases](https://github.com/RafaTGG/antiafk/releases)
2. Execute o arquivo `Monitor AFK.exe`

### A partir do código fonte

1. Clone o repositório:
   ```
   git clone https://github.com/RafaTGG/antiafk.git
   ```

2. Instale as dependências:
   ```
   pip install -r requirements.txt
   ```

3. Execute o aplicativo:
   ```
   python afk.py
   ```

## Como usar

1. Inicie o Monitor AFK.
2. Configure o tempo limite em minutos.
3. O aplicativo monitorará automaticamente a atividade do sistema.
4. Quando o tempo configurado de inatividade for atingido, o sistema será desligado.

### Opções adicionais:

- **Iniciar com o Windows**: Inicia o aplicativo automaticamente quando o Windows é iniciado.
- **Iniciar minimizado na bandeja**: Inicia o aplicativo oculto na bandeja do sistema.
- **Iniciar completamente oculto**: Inicia o aplicativo sem ícone visível (use CTRL+SHIFT+A para mostrar).
- **Testar Joystick**: Verifica se o joystick está funcionando corretamente.

## Licença

Este software é distribuído como software livre sob a licença [GNU General Public License v3.0](LICENSE).

## Contribuições

Contribuições são bem-vindas! Sinta-se à vontade para abrir issues ou enviar pull requests com melhorias. 