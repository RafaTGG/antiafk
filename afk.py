import time
import threading
import os
import sys
import winreg
import customtkinter as ctk
from pynput import mouse, keyboard
import pygame
import psutil
import pyautogui
import ctypes
import json

# Caminho para o arquivo de configurações
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "afk_config.json")

# Configurações padrão
DEFAULT_CONFIG = {
    "timeout": 600,  # 10 minutos em segundos
    "start_hidden": False,
    "fully_hidden": False,
    "autostart": False
}

class AFKApp:
    def __init__(self):
        # Inicializa funções para obter a última atividade do sistema no Windows
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32
        
        # Carrega as configurações
        self.config = self.load_config()
        
        self.last_activity = time.time()
        self.running = True
        self.timeout = self.config["timeout"]  # Usa o valor salvo
        self.mouse_listener = None
        self.keyboard_listener = None
        self.joystick_thread = None
        self.joysticks = []
        self.last_activity_type = "Inicialização"
        self.pulse_direction = 1  # Para controlar a animação de pulso
        self.pulse_value = 0.0  # Valor atual do pulso
        self.hidden_mode = False  # Indica se está em modo oculto
        self.fully_hidden = False  # Indica se deve ocultar até o ícone da bandeja
        self.tray_tooltip = "Monitor AFK: Ativo"  # Texto do tooltip do ícone na bandeja
        
        # Inicializa variáveis para controle de mouse
        self.last_mouse_pos = (0, 0)
        self.last_mouse_time = time.time()
        
        # Variável para controlar a última verificação de atividade
        self.last_check_time = time.time()
        
        # Adiciona throttling para controle de atualização de atividade (a cada 5 segundos)
        self.throttle_interval = 5.0  # intervalo em segundos
        self.last_activity_update_time = time.time()
        
        # Verifica argumentos de linha de comando
        for arg in sys.argv[1:]:
            if arg == "--hidden":
                self.hidden_mode = True
            elif arg == "--fully-hidden":
                self.hidden_mode = True
                self.fully_hidden = True
        
        # Inicializa o pygame para joystick
        pygame.init()
        pygame.joystick.init()
        
        # Configuração da interface
        self.window = ctk.CTk()
        self.window.title("Monitor AFK")
        self.window.geometry("450x550")  # Altura reduzida já que teremos rolagem
        
        # Configura o handler para fechamento da janela
        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Configura o tema e aparência
        ctk.set_appearance_mode("dark")  # Tema escuro
        ctk.set_default_color_theme("blue")  # Tema de cor azul
        
        # Fontes padrão para consistência
        self.titulo_font = ctk.CTkFont(size=18, weight="bold")
        self.subtitulo_font = ctk.CTkFont(size=16, weight="bold")
        self.texto_padrao_font = ctk.CTkFont(size=14)
        self.texto_pequeno_font = ctk.CTkFont(size=12)
        
        # Se estiver em modo oculto, não exibe a janela inicialmente
        if self.hidden_mode:
            self.window.withdraw()  # Oculta a janela
            # Cria um ícone na área de notificação (systray), a menos que esteja no modo totalmente oculto
            if not self.fully_hidden:
                self.create_systray_icon()
        
        # Container principal com barra de rolagem
        self.main_container = ctk.CTkFrame(self.window)
        self.main_container.pack(fill='both', expand=True)
        
        # Adicionar barra de rolagem
        self.scrollbar = ctk.CTkScrollbar(self.main_container)
        self.scrollbar.pack(side='right', fill='y')
        
        # Canvas para rolagem
        self.canvas = ctk.CTkCanvas(self.main_container, bg=self.window._apply_appearance_mode(self.window._fg_color),
                               highlightthickness=0, yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        
        # Configurar a scrollbar para rolar o canvas
        self.scrollbar.configure(command=self.canvas.yview)
        
        # Frame dentro do canvas que vai conter todos os widgets
        self.scrollable_frame = ctk.CTkFrame(self.canvas)
        self.scrollable_frame_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor='nw')
        
        # Painel principal para melhor organização dentro do frame rolável
        main_frame = ctk.CTkFrame(self.scrollable_frame)
        main_frame.pack(fill='both', expand=True, padx=15, pady=15)
        
        # Título do aplicativo
        titulo_app = ctk.CTkLabel(main_frame, text="Monitor AFK", 
                              font=self.titulo_font)
        titulo_app.pack(pady=(10, 20))
        
        # Painel de configuração de tempo
        tempo_frame = ctk.CTkFrame(main_frame)
        tempo_frame.pack(fill='x', padx=10, pady=10)
        
        self.timeout_label = ctk.CTkLabel(tempo_frame, text="Tempo limite (minutos):", 
                                       font=self.texto_padrao_font)
        self.timeout_label.pack(side='left', padx=10, pady=10)
        
        self.timeout_entry = ctk.CTkEntry(tempo_frame, width=70, font=self.texto_padrao_font)
        # Insere o valor de timeout em minutos das configurações carregadas
        self.timeout_entry.insert(0, str(self.timeout / 60))
        self.timeout_entry.pack(side='left', padx=10, pady=10)
        
        # Adiciona binding para detectar quando o usuário pressiona Enter ou sai do campo
        self.timeout_entry.bind("<Return>", self.update_timeout_from_input)
        self.timeout_entry.bind("<FocusOut>", self.update_timeout_from_input)
        
        # Painel de status
        status_frame = ctk.CTkFrame(main_frame)
        status_frame.pack(fill='x', padx=10, pady=10)
        
        self.status_label = ctk.CTkLabel(status_frame, text="Status: Monitorando", 
                                      font=self.subtitulo_font)
        self.status_label.pack(pady=10)
        
        self.time_left_label = ctk.CTkLabel(status_frame, text="Tempo restante: --:--", 
                                         font=self.subtitulo_font)
        self.time_left_label.pack(pady=10)
        
        # Barra de progresso para visualização do tempo restante
        self.progress_frame = ctk.CTkFrame(main_frame)
        self.progress_frame.pack(fill='x', padx=10, pady=10)
        
        self.timer_progress = ctk.CTkProgressBar(self.progress_frame, height=15)
        self.timer_progress.pack(fill='x', padx=20, pady=15)
        self.timer_progress.set(1.0)  # Inicia com 100%
        
        # Informação sobre a última atividade
        self.last_activity_frame = ctk.CTkFrame(main_frame)
        self.last_activity_frame.pack(fill='x', padx=10, pady=10)
        
        atividade_titulo = ctk.CTkLabel(self.last_activity_frame, text="Informações de Atividade:",
                                    font=self.texto_padrao_font, anchor="w")
        atividade_titulo.pack(fill='x', padx=10, pady=(10, 5))
        
        self.last_activity_label = ctk.CTkLabel(self.last_activity_frame, 
                                             text="Última atividade: Inicialização",
                                             font=self.texto_padrao_font, anchor="w")
        self.last_activity_label.pack(fill='x', padx=10, pady=2)
        
        self.last_activity_time_label = ctk.CTkLabel(self.last_activity_frame, 
                                                  text=f"Horário: {time.strftime('%H:%M:%S')}",
                                                  font=self.texto_padrao_font, anchor="w")
        self.last_activity_time_label.pack(fill='x', padx=10, pady=2)
        
        self.joystick_label = ctk.CTkLabel(self.last_activity_frame, 
                                        text="Joystick: Não detectado",
                                        font=self.texto_padrao_font, anchor="w")
        self.joystick_label.pack(fill='x', padx=10, pady=2)
        
        self.joystick_status_label = ctk.CTkLabel(self.last_activity_frame, 
                                               text="",
                                               font=self.texto_padrao_font, anchor="w")
        self.joystick_status_label.pack(fill='x', padx=10, pady=2)
        
        # Frame para botões principais
        button_frame = ctk.CTkFrame(main_frame)
        button_frame.pack(fill='x', padx=10, pady=10)
        
        button_frame_title = ctk.CTkLabel(button_frame, text="Controles:",
                                       font=self.texto_padrao_font, anchor="w")
        button_frame_title.pack(fill='x', padx=10, pady=5)
        
        buttons_container = ctk.CTkFrame(button_frame)
        buttons_container.pack(fill='x', padx=10, pady=5)
        
        self.start_button = ctk.CTkButton(buttons_container, 
                                       text="Iniciar Monitoramento", 
                                       command=self.toggle_monitoring,
                                       font=self.texto_padrao_font,
                                       height=32)
        self.start_button.pack(side='left', padx=5, pady=5, expand=True, fill='x')
        
        self.test_joystick_button = ctk.CTkButton(buttons_container, 
                                              text="Testar Joystick",
                                              command=self.test_joystick,
                                              font=self.texto_padrao_font,
                                              height=32)
        self.test_joystick_button.pack(side='left', padx=5, pady=5, expand=True, fill='x')
        
        # Frame para atalhos e opções
        shortcut_frame = ctk.CTkFrame(main_frame)
        shortcut_frame.pack(fill='x', padx=10, pady=10)
        
        shortcut_title = ctk.CTkLabel(shortcut_frame, text="Atalho:", 
                                    font=self.texto_padrao_font, anchor="w")
        shortcut_title.pack(fill='x', padx=10, pady=5)
        
        shortcut_label = ctk.CTkLabel(shortcut_frame, 
                                   text="CTRL+SHIFT+A para mostrar a janela",
                                   font=self.texto_padrao_font)
        shortcut_label.pack(fill='x', padx=10, pady=5)
        
        shortcut_note = ctk.CTkLabel(shortcut_frame, 
                                  text="(Útil para recuperar quando oculto)",
                                  font=self.texto_pequeno_font)
        shortcut_note.pack(fill='x', padx=10, pady=5)
        
        # Seção de configurações de inicialização
        startup_frame = ctk.CTkFrame(main_frame)
        startup_frame.pack(fill='x', padx=10, pady=10)
        
        startup_label = ctk.CTkLabel(startup_frame, text="Inicialização automática:", 
                                   font=self.subtitulo_font)
        startup_label.pack(pady=5, anchor='w')
        
        # Checkbox para iniciar com o Windows
        self.autostart_var = ctk.BooleanVar(value=self.config["autostart"])
        autostart_check = ctk.CTkCheckBox(
            startup_frame, 
            text="Iniciar com o Windows", 
            variable=self.autostart_var,
            command=self.toggle_autostart,
            font=self.texto_padrao_font
        )
        autostart_check.pack(fill='x', padx=10, pady=5, anchor='w')
        
        # Checkbox para iniciar minimizado
        self.start_hidden_var = ctk.BooleanVar(value=self.config["start_hidden"])
        start_hidden_check = ctk.CTkCheckBox(
            startup_frame, 
            text="Iniciar minimizado na bandeja", 
            variable=self.start_hidden_var,
            command=self.toggle_hidden_autostart,
            font=self.texto_padrao_font
        )
        start_hidden_check.pack(fill='x', padx=10, pady=5, anchor='w')
        
        # Checkbox para iniciar completamente oculto
        self.fully_hidden_var = ctk.BooleanVar(value=self.config["fully_hidden"])
        fully_hidden_check = ctk.CTkCheckBox(
            startup_frame, 
            text="Iniciar completamente oculto (use CTRL+SHIFT+A para exibir)", 
            variable=self.fully_hidden_var,
            command=self.toggle_fully_hidden,
            font=self.texto_padrao_font
        )
        fully_hidden_check.pack(fill='x', padx=10, pady=5, anchor='w')
        
        # Botões para visibilidade
        visibility_frame = ctk.CTkFrame(main_frame)
        visibility_frame.pack(fill='x', padx=10, pady=10)
        
        visibility_title = ctk.CTkLabel(visibility_frame, text="Visibilidade da janela:", 
                                     font=self.texto_padrao_font, anchor="w")
        visibility_title.pack(fill='x', padx=10, pady=5)
        
        # Botão para minimizar para a bandeja
        self.minimize_button = ctk.CTkButton(visibility_frame, 
                                          text="Minimizar para bandeja", 
                                          command=self.minimize_to_tray,
                                          font=self.texto_padrao_font,
                                          height=32)
        self.minimize_button.pack(fill='x', padx=10, pady=8)
        
        # Botão para ocultar completamente
        self.hide_completely_button = ctk.CTkButton(visibility_frame, 
                                                 text="Ocultar completamente", 
                                                 command=self.hide_completely,
                                                 font=self.texto_padrao_font,
                                                 height=32)
        self.hide_completely_button.pack(fill='x', padx=10, pady=8)
        
        # Configurar a função para atualizar o scroll quando o tamanho do frame mudar
        self.scrollable_frame.bind("<Configure>", self.on_frame_configure)
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        
        # Adicionar suporte para rolar com a roda do mouse
        self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)
        
        # Configura um listener de teclado global para detectar CTRL+SHIFT+A
        self.setup_global_hotkey()
        
        # Verifica se já está configurado para iniciar com o Windows
        self.check_autostart_status()
        
        # Inicia os listeners
        self.start_monitoring()
        
        # Thread de atualização da interface
        self.update_thread = threading.Thread(target=self.update_ui, daemon=True)
        self.update_thread.start()

    def create_systray_icon(self):
        try:
            # Importa apenas quando necessário para evitar dependência desnecessária
            import pystray
            from PIL import Image, ImageDraw
            
            # Cria um ícone mais bonito
            icon_size = 64
            icon = Image.new('RGBA', (icon_size, icon_size), color=(0, 0, 0, 0))
            
            # Desenha um círculo azul
            draw = ImageDraw.Draw(icon)
            draw.ellipse((4, 4, icon_size-4, icon_size-4), fill=(0, 120, 212))
            
            # Adiciona as iniciais "AFK" no centro
            draw.text((16, 20), "AFK", fill=(255, 255, 255))
            
            # Define o menu do ícone com mais opções
            menu = pystray.Menu(
                pystray.MenuItem('Mostrar janela', self.show_window),
                pystray.MenuItem('Testar Joystick', self.test_joystick_from_tray),
                pystray.MenuItem('Reiniciar monitoramento', self.restart_monitoring),
                pystray.MenuItem('Sair', self.exit_app)
            )
            
            # Cria o ícone na bandeja
            self.tray_icon = pystray.Icon("afk_monitor", icon, self.tray_tooltip, menu)
            
            # Inicia o ícone em uma thread separada
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except ImportError:
            print("Biblioteca pystray não encontrada. O ícone na bandeja não será exibido.")
            # Se não conseguir criar o ícone, mostre a janela
            self.hidden_mode = False
            self.window.deiconify()

    def show_window(self):
        """Mostra a janela principal"""
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def exit_app(self):
        """Encerra o aplicativo a partir do ícone da bandeja"""
        try:
            self.tray_icon.stop()
        except:
            pass
        self.exit_application()

    def minimize_to_tray(self):
        """Minimiza a aplicação para a bandeja do sistema"""
        self.window.withdraw()
        # Garante que o tray icon existe
        if not hasattr(self, 'tray_icon'):
            self.create_systray_icon()

    def hide_completely(self):
        """Oculta a aplicação completamente, sem ícone na bandeja"""
        self.window.withdraw()
        
        # Remove o ícone da bandeja se existir
        if hasattr(self, 'tray_icon'):
            try:
                self.tray_icon.stop()
                del self.tray_icon
            except:
                pass
        
        # Exibe mensagem informativa sobre o atalho
        info_dialog = ctk.CTkToplevel(self.window)
        info_dialog.title("Monitor AFK Oculto")
        info_dialog.geometry("450x180")
        info_dialog.resizable(False, False)
        
        # Torna a janela modal
        info_dialog.transient(self.window)
        info_dialog.grab_set()
        
        # Centraliza em relação à tela
        info_dialog.geometry(f"+{self.window.winfo_screenwidth()//2 - 225}+{self.window.winfo_screenheight()//2 - 90}")
        
        # Frame principal
        info_frame = ctk.CTkFrame(info_dialog)
        info_frame.pack(fill='both', expand=True, padx=15, pady=15)
        
        # Adiciona a mensagem
        message = ctk.CTkLabel(info_frame, 
                            text="O Monitor AFK foi completamente ocultado.",
                            font=self.subtitulo_font)
        message.pack(pady=(15, 5))
        
        # Instrução
        instrucao = ctk.CTkLabel(info_frame,
                              text="Para reabri-lo, pressione CTRL+SHIFT+A.",
                              font=self.texto_padrao_font)
        instrucao.pack(pady=5)
        
        # Botão para fechar
        ok_btn = ctk.CTkButton(
            info_frame, 
            text="OK", 
            command=info_dialog.destroy,
            font=self.texto_padrao_font,
            height=32,
            width=100
        )
        ok_btn.pack(pady=15)
        
        # Define o foco no botão OK
        ok_btn.focus_set()
        
        # Configura o comportamento ao pressionar Esc
        info_dialog.bind("<Escape>", lambda e: info_dialog.destroy())
        
        # A mensagem se fechará automaticamente após 5 segundos
        info_dialog.after(5000, info_dialog.destroy)

    def check_autostart_status(self):
        """Verifica se o programa está configurado para iniciar com o Windows"""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                                r"Software\Microsoft\Windows\CurrentVersion\Run", 
                                0, winreg.KEY_READ)
            try:
                value, _ = winreg.QueryValueEx(key, "AFKMonitor")
                # Atualiza o checkbox e a configuração
                self.autostart_var.set(True)
                self.config["autostart"] = True
                
                # Verifica se está configurado para iniciar em modo oculto
                if "--hidden" in value:
                    self.start_hidden_var.set(True)
                    self.config["start_hidden"] = True
                else:
                    self.start_hidden_var.set(False)
                    self.config["start_hidden"] = False
                    
                # Verifica se está configurado para ocultar completamente
                if "--fully-hidden" in value:
                    self.fully_hidden_var.set(True)
                    self.config["fully_hidden"] = True
                else:
                    self.fully_hidden_var.set(False)
                    self.config["fully_hidden"] = False
                
                # Salva as configurações para sincronizar
                self.save_config()
            except WindowsError:
                # Mantém os valores das configurações carregadas do arquivo
                pass
            winreg.CloseKey(key)
        except WindowsError:
            # Mantém os valores das configurações carregadas do arquivo
            pass

    def toggle_autostart(self):
        """Configurar ou remover inicialização automática do Windows"""
        # Atualiza e salva a configuração
        self.config["autostart"] = self.autostart_var.get()
        self.save_config()
        
        # Aplica a configuração no registro do Windows
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                                r"Software\Microsoft\Windows\CurrentVersion\Run", 
                                0, winreg.KEY_SET_VALUE)
            
            if self.autostart_var.get():
                # Adiciona ao registro
                executable_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(sys.argv[0])
                
                # Adiciona os argumentos apropriados
                if self.fully_hidden_var.get():
                    command = f'"{executable_path}" --fully-hidden'
                elif self.start_hidden_var.get():
                    command = f'"{executable_path}" --hidden'
                else:
                    command = f'"{executable_path}"'
                
                winreg.SetValueEx(key, "AFKMonitor", 0, winreg.REG_SZ, command)
            else:
                # Remove do registro
                try:
                    winreg.DeleteValue(key, "AFKMonitor")
                except WindowsError:
                    pass
            
            winreg.CloseKey(key)
        except Exception as e:
            print(f"Erro ao configurar inicialização automática: {e}")

    def toggle_hidden_autostart(self):
        """Atualiza configurações quando alterar o modo de iniciar oculto"""
        # Atualiza as configurações em memória
        self.config["start_hidden"] = self.start_hidden_var.get()
        
        # Se desmarcar "iniciar oculto", também desmarca "totalmente oculto"
        if not self.start_hidden_var.get():
            self.fully_hidden_var.set(False)
            self.config["fully_hidden"] = False
        
        # Salva as configurações
        self.save_config()
        
        # Atualiza o registro se autostart estiver ativado
        if self.autostart_var.get():
            self.toggle_autostart()

    def toggle_fully_hidden(self):
        """Atualiza configurações quando alterar o modo totalmente oculto"""
        # Atualiza as configurações em memória
        self.config["fully_hidden"] = self.fully_hidden_var.get()
        
        # Se marcar "totalmente oculto", também marca "iniciar oculto"
        if self.fully_hidden_var.get():
            self.start_hidden_var.set(True)
            self.config["start_hidden"] = True
        
        # Salva as configurações
        self.save_config()
        
        # Atualiza o registro se autostart estiver ativado
        if self.autostart_var.get():
            self.toggle_autostart()

    def update_activity(self, activity_type="Atividade detectada"):
        """Centraliza e controla a atualização da última atividade com throttling"""
        current_time = time.time()
        # Só atualiza a atividade se passou o intervalo de throttling
        if current_time - self.last_activity_update_time >= self.throttle_interval:
            self.last_activity = current_time
            self.last_activity_type = activity_type
            self.update_activity_display()
            self.last_activity_update_time = current_time
            return True
        return False

    def on_activity(self, *args):
        # Atualiza a atividade com throttling
        self.update_activity("Mouse ou teclado")

    def on_mouse_move(self, x, y):
        # Verifica se passou tempo mínimo desde o último evento processado
        current_time = time.time()
        if current_time - self.last_mouse_time < 0.1:  # Ignorar eventos muito frequentes (menos de 100ms)
            return
            
        # Verifica se o movimento foi significativo
        if self.last_mouse_pos != (0, 0):  # Ignora a primeira vez
            dx = abs(x - self.last_mouse_pos[0])
            dy = abs(y - self.last_mouse_pos[1])
            
            # Só registra se o movimento for maior que um limiar
            if dx > 10 or dy > 10:
                # Aplica throttling na atualização
                self.update_activity("Movimento do mouse")
                
        # Atualiza a posição e tempo para o próximo evento
        self.last_mouse_pos = (x, y)
        self.last_mouse_time = current_time

    def update_activity_display(self):
        # Atualiza os labels de última atividade
        current_time = time.strftime("%H:%M:%S")
        self.last_activity_label.configure(
            text=f"Última atividade: {self.last_activity_type}",
            font=self.texto_padrao_font
        )
        self.last_activity_time_label.configure(
            text=f"Horário: {current_time}",
            font=self.texto_padrao_font
        )
        
        # Força atualização imediata da interface
        self.window.update_idletasks()

    def initialize_joysticks(self):
        # Limpa a lista atual de joysticks
        self.joysticks = []
        
        # Verifica quantos joysticks estão conectados
        joystick_count = pygame.joystick.get_count()
        
        if joystick_count > 0:
            # Inicializa cada joystick
            for i in range(joystick_count):
                joystick = pygame.joystick.Joystick(i)
                joystick.init()
                self.joysticks.append(joystick)
                
            self.joystick_label.configure(
                text=f"Joystick: {joystick_count} detectado(s)",
                font=self.texto_padrao_font,
                text_color="#00AA00"  # Verde para indicar positivo
            )
        else:
            self.joystick_label.configure(
                text="Joystick: Não detectado",
                font=self.texto_padrao_font,
                text_color="#FFA500"  # Laranja para indicar atenção
            )

    def check_joystick(self):
        # Inicializa os joysticks no início
        self.initialize_joysticks()
        
        last_reinit = time.time()
        last_event_check = time.time()
        joystick_active = False
        
        while self.running:
            current_time = time.time()
            
            # A cada 5 segundos, verifica novamente os joysticks conectados
            if current_time - last_reinit > 5:
                self.initialize_joysticks()
                last_reinit = current_time
            
            # Limite a frequência de verificação de eventos para 4 vezes por segundo (250ms)
            if current_time - last_event_check > 0.25:
                last_event_check = current_time
                
                # Processa todos os eventos do pygame
                for event in pygame.event.get():
                    # Verificar botões pressionados
                    if event.type == pygame.JOYBUTTONDOWN:
                        self.update_activity("Botão do joystick")
                        joystick_active = True
                    
                    # Verificar movimentos nos eixos analógicos
                    elif event.type == pygame.JOYAXISMOTION:
                        # Apenas considerar movimentos significativos (acima de um limiar)
                        if abs(event.value) > 0.2:
                            self.update_activity("Movimento do joystick")
                            joystick_active = True
                    
                    # Verificar direcional digital
                    elif event.type == pygame.JOYHATMOTION:
                        if event.value != (0, 0):
                            self.update_activity("Direcional do joystick")
                            joystick_active = True
                    
                    # Verificar quando um joystick é conectado
                    elif event.type == pygame.JOYDEVICEADDED:
                        self.initialize_joysticks()
                        self.update_activity("Joystick conectado")
                    
                    # Verificar quando um joystick é desconectado
                    elif event.type == pygame.JOYDEVICEREMOVED:
                        self.initialize_joysticks()
                        self.update_activity("Joystick desconectado")
                
                # Verificação mais lenta, apenas a cada 1 segundo
                if current_time - getattr(self, 'last_manual_joystick_check', 0) > 1.0:
                    self.last_manual_joystick_check = current_time
                    
                    # Verificação manual para casos em que os eventos não são capturados
                    if self.joysticks:
                        for joystick in self.joysticks:
                            try:
                                # Verifica os botões
                                for i in range(joystick.get_numbuttons()):
                                    if joystick.get_button(i):
                                        self.update_activity("Botão do joystick")
                                
                                # Verifica os eixos
                                for i in range(joystick.get_numaxes()):
                                    if abs(joystick.get_axis(i)) > 0.2:
                                        self.update_activity("Movimento do joystick")
                                
                                # Verifica os hats (direcionais)
                                for i in range(joystick.get_numhats()):
                                    if joystick.get_hat(i) != (0, 0):
                                        self.update_activity("Direcional do joystick")
                            except pygame.error:
                                # O joystick pode ter sido desconectado durante a verificação
                                self.initialize_joysticks()
            
            # Atualiza a interface se houver atividade do joystick
            if joystick_active:
                joystick_active = False
            
            # Pausa para reduzir a carga da CPU
            time.sleep(0.1)

    def start_monitoring(self):
        """Inicia o monitoramento de atividade do sistema"""
        # Reinicia os listeners se necessário
        if self.mouse_listener is None or not self.mouse_listener.is_alive():
            # Configura listener para os eventos de mouse para detecção de movimento
            self.mouse_listener = mouse.Listener(on_move=self.on_mouse_move)
            self.mouse_listener.daemon = True
            self.mouse_listener.start()
        
        if self.keyboard_listener is None or not self.keyboard_listener.is_alive():
            # Configura listener para os eventos de teclado
            self.keyboard_listener = keyboard.Listener(on_press=self.on_activity, on_release=self.on_activity)
            self.keyboard_listener.daemon = True
            self.keyboard_listener.start()
        
        # Inicializa thread para verificar atividade periodicamente
        # Esta checagem serve como backup para o caso dos listeners não detectarem alguma atividade
        if not hasattr(self, 'monitoring_thread') or self.monitoring_thread is None or not self.monitoring_thread.is_alive():
            self.monitoring_thread = threading.Thread(target=self.check_activity_periodically, daemon=True)
            self.monitoring_thread.start()
        
        # Define explicitamente a última atividade como agora, para iniciar o contador
        # corretamente. Isso é crítico para o funcionamento do temporizador.
        # Como é inicialização, forçamos sem throttling
        precise_now = time.time()
        self.last_activity = precise_now
        self.last_activity_type = "Monitoramento iniciado"
        self.last_activity_update_time = precise_now  # Atualiza também o tempo de throttling
        
        print(f"Monitoramento iniciado em: {time.strftime('%H:%M:%S')}")
        print(f"Último timestamp de atividade definido para: {precise_now}")
        
        # Força atualização da interface
        self.update_activity_display()

    def check_activity_periodically(self):
        """Verifica a atividade do sistema em intervalos regulares"""
        # Configurações para o monitoramento periódico
        CHECK_INTERVAL = 5.0      # Verificar a cada 5 segundos conforme solicitado
        
        # Estados iniciais
        last_mouse_pos = pyautogui.position()  # Captura posição inicial do mouse
        last_check_time = time.time()
        
        # Define o tempo inicial de atividade
        precise_now = time.time()
        self.last_activity = precise_now
        self.last_activity_update_time = precise_now
        
        # Estrutura para obter o tempo do último input no Windows
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [
                ('cbSize', ctypes.c_uint),
                ('dwTime', ctypes.c_uint),
            ]
        
        lastInputInfo = LASTINPUTINFO()
        lastInputInfo.cbSize = ctypes.sizeof(lastInputInfo)
        
        # Obtém o tempo inicial de input do sistema
        self.user32.GetLastInputInfo(ctypes.byref(lastInputInfo))
        last_system_input_time = lastInputInfo.dwTime
        
        # Força uma atualização inicial da interface
        self.update_activity_display()
        
        # Log inicial
        print(f"Monitoramento iniciado. Tempo limite: {self.timeout/60} minutos")
        print(f"Verificando atividade a cada {CHECK_INTERVAL} segundos")
        
        while self.running:
            current_time = time.time()
            activity_detected = False
            
            # 1. Verificação rápida usando a API do Windows para qualquer input
            if self.user32.GetLastInputInfo(ctypes.byref(lastInputInfo)):
                current_system_input_time = lastInputInfo.dwTime
                
                # Verifica se houve uma mudança real no tempo de input do sistema
                if current_system_input_time != last_system_input_time:
                    # Input detectado no sistema!
                    activity_detected = True
                    if self.update_activity("Entrada do sistema"):
                        last_system_input_time = current_system_input_time
            
            # 2. Se não detectou atividade via API, verifica o mouse manualmente
            if not activity_detected:
                try:
                    current_pos = pyautogui.position()
                    
                    # Detecta se o mouse se moveu significativamente
                    if (abs(current_pos[0] - last_mouse_pos[0]) > 10 or 
                        abs(current_pos[1] - last_mouse_pos[1]) > 10):
                        activity_detected = True
                        self.update_activity("Movimento do mouse")
                    
                    # Atualiza a posição para a próxima verificação
                    last_mouse_pos = current_pos
                except Exception as e:
                    print(f"Erro ao verificar mouse: {e}")
            
            # 3. Se ainda não detectou atividade, verifica o joystick - RESTAURADO PARA VERIFICAÇÃO COMPLETA
            if not activity_detected:
                # Atualiza a lista de joysticks conectados periodicamente
                if current_time - getattr(self, 'last_joystick_init', 0) > 5.0:
                    self.initialize_joysticks()
                    self.last_joystick_init = current_time
                
                # Verifica o estado atual de cada joystick
                if self.joysticks:
                    for joy in self.joysticks:
                        try:
                            # Verifica todos os botões
                            for i in range(joy.get_numbuttons()):
                                if joy.get_button(i):
                                    activity_detected = True
                                    self.update_activity("Botão do joystick")
                                    break
                            
                            # Verifica todos os eixos analógicos
                            if not activity_detected:
                                for i in range(joy.get_numaxes()):
                                    if abs(joy.get_axis(i)) > 0.2:
                                        activity_detected = True
                                        self.update_activity("Movimento do joystick")
                                        break
                            
                            # Verifica todos os direcionais
                            if not activity_detected:
                                for i in range(joy.get_numhats()):
                                    if joy.get_hat(i) != (0, 0):
                                        activity_detected = True
                                        self.update_activity("Direcional do joystick")
                                        break
                        except pygame.error:
                            # Ignora erros de joystick desconectado
                            pass
            
            # Processa eventos do pygame sem bloqueio
            pygame.event.pump()
            
            # Se detectou atividade, atualize o display
            if activity_detected:
                # O display já foi atualizado pelo update_activity se necessário
                pass
                # Log reduzido para não sobrecarregar o console
                # print(f"Atividade detectada: {self.last_activity_type}")
            
            # A principal mudança: sempre espera o mesmo intervalo fixo de 5 segundos
            # independentemente de ter detectado atividade ou não
            time.sleep(CHECK_INTERVAL)

    def stop_monitoring(self):
        """Para o monitoramento"""
        # Desativa a flag para interromper os loops
        self.running = False
        
        # Limpa recursos
        # Limpa a lista de joysticks
        for joystick in self.joysticks:
            try:
                joystick.quit()
            except:
                pass
        self.joysticks = []
        
        # Atualiza a interface
        self.status_label.configure(text="Status: Parado")
        self.joystick_label.configure(text="Joystick: Não detectado")
        
        # Atualiza o tooltip do ícone na bandeja
        self.update_tray_tooltip("Monitor AFK: Parado")
        
        # Remove referências
        if hasattr(self, 'monitoring_thread') and self.monitoring_thread:
            self.monitoring_thread = None

    def toggle_monitoring(self):
        if self.running:
            self.stop_monitoring()
            self.start_button.configure(text="Iniciar Monitoramento")
            self.status_label.configure(text="Status: Parado")
        else:
            self.running = True
            # Resetar o tempo da última atividade ao iniciar o monitoramento
            # Forçando sem throttling por ser inicialização
            precise_now = time.time()
            self.last_activity = precise_now
            self.last_activity_type = "Monitoramento iniciado"
            self.last_activity_update_time = precise_now
            self.update_activity_display()
            
            self.start_monitoring()
            self.start_button.configure(text="Parar Monitoramento")
            self.status_label.configure(text="Status: Monitorando")
            self.update_tray_tooltip("Monitor AFK: Ativo")

    def update_ui(self):
        """Thread para atualizar a interface do usuário e verificar o tempo de inatividade"""
        last_shutdown_check = 0
        last_display_time = 0
        pulse_speed = 0.05
        
        # Força atualização inicial
        self.last_activity = time.time()
        self.update_activity_display()
        
        print("Thread de atualização da interface iniciada")
        
        while True:
            try:
                if self.running:
                    # Captura o valor atual do último tempo de atividade
                    current_last_activity = self.last_activity
                    current_time = time.time()
                    
                    # Calcula o tempo de inatividade atual
                    time_inactive = current_time - current_last_activity
                    
                    # Calcula tempo restante (regressivo)
                    time_left = max(0, self.timeout - time_inactive)
                    
                    # Atualiza a barra de progresso (sem animações complexas para a maioria dos casos)
                    progress_ratio = time_left / self.timeout if self.timeout > 0 else 0
                    progress_ratio = max(0, min(1, progress_ratio))  # Garante que o valor está entre 0 e 1
                    
                    # Simplifica o efeito de pulso - apenas para os últimos 30 segundos
                    if time_left < 30:  # Animação só nos últimos 30 segundos
                        self.pulse_value += pulse_speed * self.pulse_direction
                        if self.pulse_value >= 1.0 or self.pulse_value <= 0.0:
                            self.pulse_direction *= -1  # Inverte a direção
                            self.pulse_value = max(0.0, min(1.0, self.pulse_value))
                        
                        # Cores de alerta simplificadas
                        self.timer_progress.configure(progress_color="#FF0000")  # Vermelho fixo
                    else:
                        # Configuração mais simples para o resto do tempo
                        self.timer_progress.set(progress_ratio)
                        if progress_ratio < 0.3:
                            self.timer_progress.configure(progress_color="#FF0000")  # Vermelho
                        else:
                            self.timer_progress.configure(progress_color="#1F6AA5")  # Azul padrão
                    
                    # Formata o tempo
                    minutes = int(time_left // 60)
                    seconds = int(time_left % 60)
                    
                    # Atualiza a interface em intervalos mais espaçados (a cada segundo, não a cada frame)
                    current_second = int(time_left)
                    if current_second != last_display_time:
                        # Atualiza o texto do tempo restante
                        timer_text = f"Tempo restante: {minutes:02d}:{seconds:02d}"
                        self.time_left_label.configure(text=timer_text)
                        
                        # Atualiza o tooltip com menor frequência
                        if current_second % 30 == 0 or current_second < 60:
                            self.update_tray_tooltip(f"Monitor AFK: {minutes:02d}:{seconds:02d} restantes")
                        
                        # Cor do texto simplificada
                        if time_left < 60:
                            self.time_left_label.configure(text_color="#FF0000")  # Vermelho para alertar
                        else:
                            self.time_left_label.configure(text_color=None)  # Cor padrão
                        
                        last_display_time = current_second
                    
                    # Verificação de tempo limite para desligamento
                    if time_inactive >= self.timeout:
                        # Verifica a cada 5 segundos (em vez de constantemente)
                        if current_time - last_shutdown_check > 5:
                            last_shutdown_check = current_time
                            
                            print(f"Tempo limite atingido! Inativo por {time_inactive:.1f} segundos")
                            
                            # Prepara para desligar
                            self.time_left_label.configure(
                                text="DESLIGANDO O SISTEMA", 
                                text_color="#FF0000",
                                font=self.titulo_font
                            )
                            self.status_label.configure(
                                text="Status: Desligando...",
                                text_color="#FF0000"
                            )
                            self.window.update()
                            
                            # Cria aviso de desligamento
                            self.show_shutdown_warning()
                            
                            # Para o monitoramento e inicia o desligamento
                            self.stop_monitoring()
                            os.system("shutdown /s /t 1")
                            break
            except Exception as e:
                print(f"Erro na atualização da UI: {e}")
            
            # Intervalo mais longo entre atualizações da interface (500ms em vez de 200ms)
            time.sleep(0.5)

    def show_shutdown_warning(self):
        """Mostra um aviso de que o sistema será desligado"""
        try:
            # Cria uma janela de aviso em tela cheia
            warning = ctk.CTkToplevel()
            warning.title("DESLIGANDO")
            warning.attributes('-fullscreen', True)
            
            # Define a cor de fundo para vermelho
            warning.configure(fg_color="#FF0000")
            
            # Centraliza a mensagem
            warning_frame = ctk.CTkFrame(warning, fg_color="#FF0000", border_width=0)
            warning_frame.pack(expand=True, fill='both')
            
            # Adiciona a mensagem de aviso
            message = ctk.CTkLabel(
                warning_frame, 
                text="SISTEMA SENDO DESLIGADO",
                font=ctk.CTkFont(size=50, weight="bold"),
                text_color="#FFFFFF"
            )
            message.pack(expand=True)
            
            # Atualiza a tela
            warning.update()
        except:
            # Ignora erros na criação do aviso, pois o sistema será desligado de qualquer forma
            pass

    def test_joystick(self):
        # Atualiza a lista de joysticks
        self.initialize_joysticks()
        
        if not self.joysticks:
            self.joystick_status_label.configure(
                text="Nenhum joystick detectado. Verifique a conexão.",
                font=self.texto_padrao_font
            )
            return
        
        # Inicia uma verificação de 5 segundos para detectar entradas
        test_start = time.time()
        self.joystick_status_label.configure(
            text="Teste iniciado. Mova ou pressione botões no joystick...",
            font=self.texto_padrao_font
        )
        self.window.update()
        
        detected_activity = False
        while time.time() - test_start < 5 and not detected_activity:
            # Processa todos os eventos do pygame
            for event in pygame.event.get():
                if event.type in [pygame.JOYBUTTONDOWN, pygame.JOYAXISMOTION, pygame.JOYHATMOTION]:
                    detected_activity = True
                    break
            
            # Verificação manual
            for joystick in self.joysticks:
                try:
                    # Verifica os botões
                    for i in range(joystick.get_numbuttons()):
                        if joystick.get_button(i):
                            detected_activity = True
                            break
                    
                    # Verifica os eixos
                    if not detected_activity:
                        for i in range(joystick.get_numaxes()):
                            if abs(joystick.get_axis(i)) > 0.2:
                                detected_activity = True
                                break
                    
                    # Verifica os hats (direcionais)
                    if not detected_activity:
                        for i in range(joystick.get_numhats()):
                            if joystick.get_hat(i) != (0, 0):
                                detected_activity = True
                                break
                except pygame.error:
                    pass
                
                if detected_activity:
                    break
            
            self.window.update()
            time.sleep(0.1)
        
        if detected_activity:
            self.joystick_status_label.configure(
                text="Teste concluído: Joystick funcionando corretamente!",
                font=self.texto_padrao_font,
                text_color="green"
            )
            # Atualiza o tempo de última atividade - ignorando throttling por ser teste
            precise_now = time.time()
            self.last_activity = precise_now
            self.last_activity_type = "Teste de joystick"
            self.last_activity_update_time = precise_now
            self.update_activity_display()
        else:
            self.joystick_status_label.configure(
                text="Nenhuma atividade detectada. Verifique se o joystick está funcionando.",
                font=self.texto_padrao_font,
                text_color="red"
            )
        
        # Agenda limpeza do texto após 5 segundos
        self.window.after(5000, lambda: self.joystick_status_label.configure(text=""))

    def test_joystick_from_tray(self):
        """Função para testar o joystick a partir do menu da bandeja"""
        # Primeiro mostra a janela
        self.show_window()
        # Depois executa o teste
        self.test_joystick()

    def restart_monitoring(self):
        """Reinicia o monitoramento a partir do menu da bandeja"""
        self.stop_monitoring()
        time.sleep(0.5)  # Pequena pausa para garantir que tudo foi parado
        self.running = True
        
        # Resetar o tempo da última atividade ao reiniciar o monitoramento
        # Ignorando throttling por ser reinicialização
        precise_now = time.time()
        self.last_activity = precise_now
        self.last_activity_type = "Monitoramento reiniciado"
        self.last_activity_update_time = precise_now
        self.update_activity_display()
        
        self.start_monitoring()
        self.update_tray_tooltip("Monitor AFK: Ativo")

    def update_tray_tooltip(self, text):
        """Atualiza o tooltip do ícone na bandeja"""
        if hasattr(self, 'tray_icon'):
            try:
                self.tray_tooltip = text
                self.tray_icon.title = text
            except:
                pass

    def on_frame_configure(self, event):
        """Atualiza a região rolável do canvas quando o frame interior muda de tamanho"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    
    def on_canvas_configure(self, event):
        """Redimensiona o frame interior quando o canvas é redimensionado"""
        # Atualiza a largura do frame interior para preencher o canvas
        self.canvas.itemconfig(self.scrollable_frame_window, width=event.width)
    
    def on_mousewheel(self, event):
        """Permite rolar com a roda do mouse"""
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def exit_application(self):
        """Encerra o aplicativo"""
        # Para todos os monitoramentos
        self.stop_monitoring()
        
        # Encerra o pygame
        try:
            pygame.quit()
        except:
            pass
        
        # Encerra o ícone da bandeja se existir
        if hasattr(self, 'tray_icon'):
            try:
                self.tray_icon.stop()
            except:
                pass
        
        # Destrói a janela e encerra o programa
        self.window.destroy()
        sys.exit(0)

    def on_closing(self):
        """Função chamada quando a janela é fechada"""
        # Verifica se já existe um diálogo aberto
        for widget in self.window.winfo_children():
            if isinstance(widget, ctk.CTkToplevel):
                return  # Já existe um diálogo, não cria outro
        
        # Cria diálogo simples para evitar problemas com widgets complexos
        dialog = ctk.CTkToplevel(self.window)
        dialog.title("Fechar Monitor AFK")
        dialog.geometry("450x200")
        dialog.resizable(False, False)
        dialog.transient(self.window)
        dialog.grab_set()
        
        # Centraliza o diálogo
        x = self.window.winfo_x() + (self.window.winfo_width() // 2) - (450 // 2)
        y = self.window.winfo_y() + (self.window.winfo_height() // 2) - (200 // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Cria widgets do diálogo
        label = ctk.CTkLabel(dialog, text="O que você deseja fazer?", font=self.subtitulo_font)
        label.pack(pady=(20, 30))
        
        # Botões simplificados 
        button_frame = ctk.CTkFrame(dialog)
        button_frame.pack(fill="x", padx=20, pady=10)
        
        # Cada botão em seu próprio frame para evitar problemas de destruição de widgets
        min_button = ctk.CTkButton(button_frame, text="Minimizar para bandeja", 
                                font=self.texto_padrao_font, height=32,
                                command=lambda: [dialog.destroy(), self.minimize_to_tray()])
        min_button.pack(side="left", padx=5, pady=5, expand=True, fill="x")
        
        hide_button = ctk.CTkButton(button_frame, text="Ocultar completamente", 
                                 font=self.texto_padrao_font, height=32,
                                 command=lambda: [dialog.destroy(), self.hide_completely()])
        hide_button.pack(side="left", padx=5, pady=5, expand=True, fill="x")
        
        exit_button = ctk.CTkButton(button_frame, text="Sair completamente", 
                                 font=self.texto_padrao_font, height=32,
                                 command=lambda: [dialog.destroy(), self.exit_application()])
        exit_button.pack(side="left", padx=5, pady=5, expand=True, fill="x")
        
        # Configura tecla ESC para minimizar para bandeja
        dialog.bind("<Escape>", lambda e: [dialog.destroy(), self.minimize_to_tray()])

    def setup_global_hotkey(self):
        """Configura um listener global para detectar o atalho CTRL+SHIFT+A"""
        # Usamos uma abordagem diferente para o hotkey, já que é fundamental
        # que ele funcione mesmo quando o resto do monitoramento está pausado
        self.hotkey_thread = threading.Thread(target=self.hotkey_listener, daemon=True)
        self.hotkey_thread.start()
    
    def hotkey_listener(self):
        """Thread para monitorar o atalho CTRL+SHIFT+A para mostrar a janela"""
        from pynput import keyboard
        
        # Define as teclas a serem monitoradas
        COMBINATIONS = [
            {keyboard.Key.ctrl_l, keyboard.Key.shift, keyboard.KeyCode(char='a')},
            {keyboard.Key.ctrl_l, keyboard.Key.shift, keyboard.KeyCode(char='A')},
            {keyboard.Key.ctrl_r, keyboard.Key.shift, keyboard.KeyCode(char='a')},
            {keyboard.Key.ctrl_r, keyboard.Key.shift, keyboard.KeyCode(char='A')}
        ]
        
        # Conjunto para guardar as teclas pressionadas
        current = set()
        
        def on_press(key):
            if key in {keyboard.Key.ctrl_l, keyboard.Key.ctrl_r, keyboard.Key.shift, 
                    keyboard.KeyCode(char='a'), keyboard.KeyCode(char='A')}:
                current.add(key)
                for combination in COMBINATIONS:
                    if all(k in current for k in combination):
                        # Chama a função para mostrar a janela na thread principal
                        self.window.after(0, self.show_window)
        
        def on_release(key):
            try:
                current.remove(key)
            except KeyError:
                pass
        
        # Inicia o listener global
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()

    def run(self):
        self.window.mainloop()

    def load_config(self):
        """Carrega as configurações do arquivo JSON"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    return json.load(f)
            else:
                return DEFAULT_CONFIG.copy()
        except Exception as e:
            print(f"Erro ao carregar configurações: {e}")
            return DEFAULT_CONFIG.copy()
    
    def save_config(self):
        """Salva as configurações atuais no arquivo JSON"""
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Erro ao salvar configurações: {e}")
    
    def update_timeout_from_input(self, *args):
        """Atualiza o valor do timeout quando o usuário muda o input"""
        try:
            # Obtém o valor atual do campo de entrada (em minutos)
            minutes = float(self.timeout_entry.get())
            # Converte para segundos e armazena
            self.timeout = minutes * 60
            # Atualiza a configuração
            self.config["timeout"] = self.timeout
            # Salva as configurações
            self.save_config()
            
            # Importante: reseta o tempo da última atividade para que o cronômetro 
            # comece a contar a partir de agora com o novo valor
            # Forçando sem throttling por ser alteração manual do usuário
            precise_now = time.time()
            self.last_activity = precise_now
            self.last_activity_type = "Tempo alterado pelo usuário"
            self.last_activity_update_time = precise_now
            self.update_activity_display()
            
            print(f"Timeout atualizado para {minutes} minutos ({self.timeout} segundos) e salvo")
        except ValueError:
            # Se o valor não for um número válido, mantém o timeout atual
            print(f"Valor de timeout inválido, mantendo {self.timeout/60} minutos")
            # Redefine o campo para o valor atual válido
            self.timeout_entry.delete(0, ctk.END)
            self.timeout_entry.insert(0, str(self.timeout/60))

if __name__ == "__main__":
    app = AFKApp()
    app.run() 