"""
Página para atualização de bancos de dados.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFormLayout, QMessageBox, QTextEdit, QFileDialog, QLineEdit
)
from PySide6.QtCore import Qt, QThread, Signal
import os
import subprocess
import sys
from core.shared.paths import get_base_dir

# Diretório do testezudo = mesma fonte que a aba TESTE (Dota Draft)
try:
    from core.dota.draft_testezudo import TESTEZUDO_DIR
except Exception:
    TESTEZUDO_DIR = os.path.join(os.path.expanduser("~"), "Documents", "testezudo")


# Nome padrão do CSV de 2026 (usado para busca na pasta do .exe)
DEFAULT_CSV_NAME = "2026_LoL_esports_match_data_from_OraclesElixir.csv"


def _find_default_csv():
    """
    Encontra o CSV de LoL nos locais padrão.
    Prioridade: pasta do .exe (quando empacotado) > db2026 > data do projeto.
    Retorna o caminho ou None.
    """
    search_locations = []

    # PRIORIDADE 1: Pasta do .exe (quando empacotado) - onde o usuário coloca o CSV
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        search_locations.append(exe_dir)
        # Se o exe está em _internal, a pasta "do usuário" pode ser o pai
        if "_internal" in exe_dir:
            exe_parent = os.path.dirname(exe_dir)
            search_locations.insert(0, exe_parent)  # Pasta pai tem prioridade

    # PRIORIDADE 2: db2026 (localização conhecida)
    search_locations.append(r"C:\Users\Lucas\Documents\db2026")

    # PRIORIDADE 3: data do projeto
    base_dir = get_base_dir()
    search_locations.append(os.path.join(base_dir, "data"))

    # Procurar o CSV em cada local
    for loc in search_locations:
        if not loc or not os.path.exists(loc):
            continue
        # Primeiro o nome exato
        path_exato = os.path.join(loc, DEFAULT_CSV_NAME)
        if os.path.isfile(path_exato):
            return path_exato
        # Depois qualquer CSV Oracle/LoL no diretório
        try:
            for f in os.listdir(loc):
                if f.endswith(".csv") and ("LoL_esports" in f or "oracle" in f.lower() or "2026" in f):
                    full = os.path.join(loc, f)
                    if os.path.isfile(full):
                        return full
        except OSError:
            pass

    return None


def find_script(script_name):
    """
    Encontra um script Python procurando em múltiplos locais.
    Funciona tanto em desenvolvimento quanto quando empacotado como .exe.
    """
    # Lista de locais para procurar
    search_locations = []
    
    # 1. Em desenvolvimento, usar o diretório do projeto
    # (voltar 4 níveis de src/app/ui/pages/database_update.py)
    current_file_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_file_dir, '..', '..', '..', '..'))
    search_locations.append(project_root)
    
    # 2. Diretório base (onde estão os dados)
    base_dir = get_base_dir()
    if base_dir not in search_locations:
        search_locations.append(base_dir)
    
    # 3. Se estiver empacotado, procurar em locais adicionais
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        
        # 4. Procurar na mesma pasta do .exe (onde os scripts são copiados pelo PyInstaller)
        search_locations.append(exe_dir)
        
        # 5. Se o .exe está em _internal, procurar na pasta pai (onde o .exe principal está)
        if '_internal' in exe_dir:
            exe_parent = os.path.dirname(exe_dir)
            if exe_parent not in search_locations:
                search_locations.append(exe_parent)
        
        # 6. Diretório pai do .exe
        parent_dir = os.path.dirname(exe_dir)
        if parent_dir not in search_locations:
            search_locations.append(parent_dir)
        
        # 7. Tentar encontrar o diretório do projeto original
        # Se o .exe está em dist/LoLOracleML/_internal, o projeto está em dist/LoLOracleML/..
        parts = exe_dir.split(os.sep)
        if 'dist' in parts:
            dist_idx = parts.index('dist')
            project_from_dist = os.sep.join(parts[:dist_idx])
            if project_from_dist not in search_locations and os.path.exists(project_from_dist):
                search_locations.append(project_from_dist)
    
    # Procurar o script em todos os locais
    for location in search_locations:
        if location and os.path.exists(location):
            script_path = os.path.join(location, script_name)
            if os.path.exists(script_path):
                return script_path
    
    # Se não encontrou, retornar o primeiro local válido (para mostrar erro)
    for location in search_locations:
        if location and os.path.exists(location):
            return os.path.join(location, script_name)
    
    # Último fallback
    return script_name


class PrebetsUpdateThread(QThread):
    """Thread para atualizar o SQLite das Pré-bets (Players e Secundárias) diretamente."""
    finished = Signal(str, bool)  # (output, success)
    error = Signal(str)  # Para compatibilidade com _on_update_error

    def __init__(self, csv_path):
        super().__init__()
        self.csv_path = csv_path

    def run(self):
        import io

        output_buffer = io.StringIO()
        old_stdout = sys.stdout
        try:
            sys.stdout = output_buffer
            from core.lol.db_converter import create_oracle_db_from_csv
            from core.shared.paths import get_data_dir, get_lol_db_path, get_lol_db2026_dir

            # Sempre igual a get_lol_db_path / pré-bets: se existir Documents/db2026, o .db fica lá.
            # O ramo "frozen" não pode forçar dist/.../lol_esports.db senão a UI lê db2026 e a
            # atualização grava noutro sítio (dados "não mudam").
            db_path = get_lol_db_path() or os.path.join(get_lol_db2026_dir(), "lol_esports.db")
            if not db_path:
                if getattr(sys, "frozen", False):
                    exe_dir = os.path.dirname(sys.executable)
                    if "_internal" in exe_dir:
                        exe_dir = os.path.dirname(exe_dir)
                    db_path = os.path.join(exe_dir, "lol_esports.db")
                else:
                    db_path = os.path.join(get_data_dir(), "lol_esports.db")
            _parent = os.path.dirname(os.path.abspath(db_path))
            if _parent:
                os.makedirs(_parent, exist_ok=True)
            create_oracle_db_from_csv(self.csv_path, db_path)
            success = True
        except Exception as e:
            import traceback
            success = False
            output_buffer.write(f"Erro: {e}\n{traceback.format_exc()}")
        finally:
            sys.stdout = old_stdout

        self.finished.emit(output_buffer.getvalue(), success)


class UpdateThread(QThread):
    """Thread para executar atualização de banco sem travar a UI."""
    finished = Signal(str, bool)  # (output, success)
    error = Signal(str)
    progress = Signal(str)  # saída incremental em tempo real

    def __init__(self, script_path, args=None, cwd=None, python_exe=None, extra_env=None):
        super().__init__()
        self.script_path = script_path
        self.args = args or []
        self.cwd = cwd
        self.python_exe = python_exe
        self.extra_env = extra_env or {}
    
    def _find_python_exe(self):
        """Encontra o python.exe do venv do projeto, não o .exe do PyInstaller."""
        if self.python_exe:
            return self.python_exe
        
        # PRIORIDADE 1: Tentar encontrar o venv do projeto atual
        # O venv está em C:\Users\Lucas\Documents\lol_oracle_ml_v3\venv
        project_venv_paths = [
            # Caminho absoluto conhecido
            r'C:\Users\Lucas\Documents\lol_oracle_ml_v3\venv\Scripts\python.exe',
        ]
        
        # Se estiver no .exe, tentar encontrar o projeto original
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            # Se está em dist/LoLOracleML/_internal, o projeto está em dist/LoLOracleML/..
            parts = exe_dir.split(os.sep)
            if 'dist' in parts:
                dist_idx = parts.index('dist')
                project_root = os.sep.join(parts[:dist_idx])
                project_venv = os.path.join(project_root, 'venv', 'Scripts', 'python.exe')
                project_venv_paths.insert(0, project_venv)
            
            # Tentar relativo ao diretório do .exe
            exe_parent = os.path.dirname(exe_dir)
            if '_internal' in exe_dir:
                # Se está em _internal, o projeto está 2 níveis acima
                project_from_exe = os.path.join(exe_dir, '..', '..', 'venv', 'Scripts', 'python.exe')
                project_venv_paths.insert(0, os.path.normpath(project_from_exe))
        
        # Procurar venv do projeto
        for venv_path in project_venv_paths:
            venv_path = os.path.normpath(venv_path)
            if os.path.exists(venv_path):
                # Verificar se tem pandas (necessário para os scripts)
                try:
                    result = subprocess.run(
                        [venv_path, '-c', 'import pandas'],
                        capture_output=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        return venv_path
                except:
                    pass
        
        # PRIORIDADE 2: Se o script está no projeto Dota, tentar usar o venv do projeto Dota
        if self.cwd and 'dota_oracle_v1' in self.cwd:
            dota_venv = os.path.join(self.cwd, 'venv', 'Scripts', 'python.exe')
            if os.path.exists(dota_venv):
                try:
                    result = subprocess.run(
                        [dota_venv, '-c', 'import selenium'],
                        capture_output=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        return dota_venv
                except:
                    pass
        
        # PRIORIDADE 3: Tentar encontrar python.exe no PATH (último recurso)
        import shutil
        python_exe = shutil.which('python')
        if python_exe:
            return python_exe
        python_exe = shutil.which('python3')
        if python_exe:
            return python_exe
        
        # Se não estiver no .exe, usar sys.executable normalmente
        return sys.executable
    
    def run(self):
        try:
            python_exe = self._find_python_exe()
            
            if not python_exe or not os.path.exists(python_exe):
                self.error.emit(f"Python não encontrado: {python_exe}\n\nVerifique se o Python está instalado e acessível.")
                return
            
            # -u força stdout/stderr não-bufferizados para log em tempo real
            cmd = [python_exe, "-u", self.script_path] + self.args
            
            # Configurar ambiente para usar UTF-8 (necessário para emojis e caracteres Unicode)
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            env['PYTHONUTF8'] = '1'
            env['PYTHONUNBUFFERED'] = '1'
            for k, v in self.extra_env.items():
                env[k] = str(v)

            output_lines = []
            process = subprocess.Popen(
                cmd,
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
                bufsize=1,
            )

            try:
                # Leitura incremental do log para não parecer travado
                if process.stdout is not None:
                    for line in process.stdout:
                        output_lines.append(line)
                        self.progress.emit(line.rstrip("\n"))
                returncode = process.wait(timeout=3600)  # Timeout de 1 hora
            except subprocess.TimeoutExpired:
                process.kill()
                raise

            output = "".join(output_lines)
            success = returncode == 0

            # Se houver erro, adicionar informações de debug
            if not success:
                output = f"[ERRO] Código de saída: {returncode}\n" + output
                output = f"[DEBUG] Comando executado: {' '.join(cmd)}\n" + output
                output = f"[DEBUG] Diretório de trabalho: {self.cwd}\n" + output
                output = f"[DEBUG] Python usado: {python_exe}\n" + output

            self.finished.emit(output, success)
        except subprocess.TimeoutExpired:
            self.error.emit("Timeout: O script demorou mais de 1 hora para executar.")
        except Exception as e:
            error_msg = f"Erro ao executar script: {str(e)}\n"
            error_msg += f"Script: {self.script_path}\n"
            error_msg += f"Args: {self.args}\n"
            error_msg += f"CWD: {self.cwd}\n"
            import traceback
            error_msg += f"Traceback: {traceback.format_exc()}"
            self.error.emit(error_msg)


class DatabaseUpdatePage(QWidget):
    """Página para atualização de bancos de dados."""
    
    def __init__(self):
        super().__init__()
        self.update_thread = None
        self.csv_path = None  # CSV selecionado ou detectado automaticamente
        self._init_ui()
    
    def _init_ui(self):
        """Inicializa a interface."""
        layout = QVBoxLayout(self)
        
        # Título
        title = QLabel("Atualizacao de Bancos de Dados")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)
        
        # Grupo LoL Pré-bets
        lol_prebets_group = QGroupBox("LoL - Pré-bets (Secundárias e Players)")
        lol_prebets_layout = QVBoxLayout()
        
        info1 = QLabel(
            "Atualiza o banco SQLite usado para pré-bets secundárias e players.\n"
            "Usa o CSV da mesma pasta do .exe (ou o selecionado na seção abaixo)."
        )
        info1.setWordWrap(True)
        lol_prebets_layout.addWidget(info1)
        
        btn1 = QPushButton("Atualizar Banco LoL Pré-bets")
        btn1.clicked.connect(self._update_lol_prebets)
        lol_prebets_layout.addWidget(btn1)
        
        lol_prebets_group.setLayout(lol_prebets_layout)
        layout.addWidget(lol_prebets_group)
        
        # Grupo LoL Draft/Compare
        lol_draft_group = QGroupBox("LoL - Draft Live e Comparar Composições")
        lol_draft_layout = QVBoxLayout()
        
        info2 = QLabel(
            "Atualiza oracle_prepared.csv e regenera todos os arquivos de estatísticas.\n"
            "O CSV é buscado automaticamente na mesma pasta do .exe (2026_LoL_esports_match_data_from_OraclesElixir.csv)."
        )
        info2.setWordWrap(True)
        lol_draft_layout.addWidget(info2)
        
        btn2_layout = QHBoxLayout()
        self.csv_path_label = QLabel("Nenhum arquivo selecionado")
        btn_select_csv = QPushButton("Selecionar CSV")
        btn_select_csv.clicked.connect(self._select_csv_file)
        btn2_layout.addWidget(self.csv_path_label)
        btn2_layout.addWidget(btn_select_csv)
        lol_draft_layout.addLayout(btn2_layout)

        # Buscar CSV automaticamente (pasta do .exe ou locais padrão)
        self._detectar_csv_padrao()
        
        btn2 = QPushButton("Atualizar Draft/Compare LoL")
        btn2.clicked.connect(self._update_lol_draft)
        lol_draft_layout.addWidget(btn2)
        
        lol_draft_group.setLayout(lol_draft_layout)
        layout.addWidget(lol_draft_group)
        
        # Grupo Dota Pré-bets
        dota_prebets_group = QGroupBox("Dota - Pré-bets Secundárias")
        dota_prebets_layout = QVBoxLayout()
        
        info3 = QLabel(
            "Atualiza o banco cyberscore.db usado para pré-bets de Dota.\n"
            "Script: import_cyberscore_completo.py\n"
            "Requer: team_id do CyberScore"
        )
        info3.setWordWrap(True)
        dota_prebets_layout.addWidget(info3)
        
        team_id_layout = QHBoxLayout()
        team_id_label = QLabel("Team ID:")
        self.team_id_input = QLineEdit()
        self.team_id_input.setPlaceholderText("Ex: 12345")
        team_id_layout.addWidget(team_id_label)
        team_id_layout.addWidget(self.team_id_input)
        dota_prebets_layout.addLayout(team_id_layout)
        
        btn3 = QPushButton("Atualizar Banco Dota Pré-bets")
        btn3.clicked.connect(self._update_dota_prebets)
        dota_prebets_layout.addWidget(btn3)
        
        dota_prebets_group.setLayout(dota_prebets_layout)
        layout.addWidget(dota_prebets_group)
        
        # Grupo Dota Draft Live
        dota_draft_group = QGroupBox("Dota - Draft Live")
        dota_draft_layout = QVBoxLayout()
        
        info4 = QLabel(
            "Atualiza o banco usado pela aba TESTE (testezudo) e recalcula os .pkl do testezudo.\n"
            "Os jogos do campeonato são adicionados na mesma DB da aba TESTE; jogos já existentes "
            "(mesmo match_id) não são duplicados (import: INSERT OR REPLACE, merge: INSERT OR IGNORE).\n"
            "Fluxo: Importar liga OpenDota → Merge → Média global → Impactos bayesianos (testezudo)\n"
            "Diretório: testezudo (mesmo da aba TESTE)\n\n"
            "Informe o League ID da OpenDota (ex: 18988) e o sistema fará todo o resto automaticamente."
        )
        info4.setWordWrap(True)
        dota_draft_layout.addWidget(info4)
        
        # Campo para League ID
        league_id_layout = QHBoxLayout()
        league_id_label = QLabel("League ID (OpenDota):")
        self.league_id_input = QLineEdit()
        self.league_id_input.setPlaceholderText("Ex: 18988")
        league_id_layout.addWidget(league_id_label)
        league_id_layout.addWidget(self.league_id_input)
        dota_draft_layout.addLayout(league_id_layout)
        
        # Campo opcional para League Name
        league_name_layout = QHBoxLayout()
        league_name_label = QLabel("League Name (opcional):")
        self.league_name_input = QLineEdit()
        self.league_name_input.setPlaceholderText("Deixe vazio para usar nome padrão")
        league_name_layout.addWidget(league_name_label)
        league_name_layout.addWidget(self.league_name_input)
        dota_draft_layout.addLayout(league_name_layout)
        
        # Campo para API Key
        api_key_layout = QHBoxLayout()
        api_key_label = QLabel("API Key OpenDota:")
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Ex: 37e714d1-52c9-49c5-97bc-5088952738e4")
        self.api_key_input.setText("37e714d1-52c9-49c5-97bc-5088952738e4")  # Preencher com a key padrão
        api_key_layout.addWidget(api_key_label)
        api_key_layout.addWidget(self.api_key_input)
        dota_draft_layout.addLayout(api_key_layout)
        
        btn4 = QPushButton("Atualizar Banco Dota Draft Live")
        btn4.clicked.connect(self._update_dota_draft)
        dota_draft_layout.addWidget(btn4)
        
        dota_draft_group.setLayout(dota_draft_layout)
        layout.addWidget(dota_draft_group)
        
        # Área de output
        output_group = QGroupBox("Log de Atualização")
        output_layout = QVBoxLayout()
        
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setFontFamily("Consolas")
        self.output_text.setMinimumHeight(300)
        output_layout.addWidget(self.output_text)
        
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)
    
    def _detectar_csv_padrao(self):
        """Detecta o CSV automaticamente na pasta do .exe ou locais padrão."""
        csv_path = _find_default_csv()
        if csv_path:
            self.csv_path = csv_path
            self.csv_path_label.setText(os.path.basename(csv_path))

    def _select_csv_file(self):
        """Seleciona arquivo CSV para atualização."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar CSV de 2026",
            "",
            "CSV Files (*.csv);;All Files (*)"
        )
        if file_path:
            self.csv_path = file_path
            self.csv_path_label.setText(os.path.basename(file_path))
    
    def _update_lol_prebets(self):
        """Atualiza banco LoL pré-bets manualmente."""
        # Usar CSV detectado ou procurar em locais padrão (pasta do .exe, db2026, data)
        csv_path = self.csv_path if (hasattr(self, "csv_path") and self.csv_path and os.path.exists(self.csv_path)) else _find_default_csv()

        if not csv_path:
            resposta = QMessageBox.question(
                self,
                "CSV não encontrado",
                "O arquivo CSV não foi encontrado em:\n\n"
                "- Pasta do .exe (mesma pasta onde está o executável)\n"
                "- C:\\Users\\Lucas\\Documents\\db2026\n"
                "- data/\n\n"
                "Coloque 2026_LoL_esports_match_data_from_OraclesElixir.csv na pasta do .exe ou selecione manualmente.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if resposta == QMessageBox.StandardButton.Yes:
                file_path, _ = QFileDialog.getOpenFileName(
                    self,
                    "Selecionar CSV de 2026",
                    "",
                    "CSV Files (*.csv);;All Files (*)"
                )
                if file_path:
                    csv_path = file_path
                else:
                    return
            else:
                return
        
        resposta = QMessageBox.question(
            self,
            "Confirmar",
            f"Atualizar banco LoL pré-bets (Willer, times, etc.) com:\n{os.path.basename(csv_path)}\n\n"
            "Isso irá atualizar o banco SQLite usado pelas Pré-bets Players e Secundárias. Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if resposta == QMessageBox.StandardButton.Yes:
            self.output_text.clear()
            self.output_text.append("Iniciando atualização do banco LoL pré-bets (SQLite)...\n")
            self.output_text.append(f"CSV: {csv_path}\n\n")

            # Executar diretamente (funciona no .exe) - atualiza lol_esports.db usado por Willer, times, etc.
            self.update_thread = PrebetsUpdateThread(csv_path)
            self.update_thread.finished.connect(self._on_update_finished)
            self.update_thread.error.connect(self._on_update_error)
            self.update_thread.start()
    
    def _update_lol_draft(self):
        """Atualiza dados LoL draft/compare."""
        # Usar CSV detectado ou procurar automaticamente (pasta do .exe, db2026, data)
        csv_path = self.csv_path if (hasattr(self, "csv_path") and self.csv_path and os.path.exists(self.csv_path)) else _find_default_csv()
        if not csv_path:
            QMessageBox.warning(
                self,
                "Erro",
                "CSV não encontrado. Coloque 2026_LoL_esports_match_data_from_OraclesElixir.csv "
                "na mesma pasta do .exe ou selecione manualmente."
            )
            return

        if not os.path.exists(csv_path):
            QMessageBox.warning(
                self,
                "Erro",
                f"Arquivo não encontrado: {csv_path}"
            )
            return

        # Encontrar o script usando find_script()
        script_path = find_script("atualizar_apenas_2026.py")
        if not os.path.exists(script_path):
            QMessageBox.warning(
                self,
                "Erro",
                f"Script não encontrado: {script_path}\n\n"
                f"Verifique se o arquivo existe no diretório do projeto."
            )
            return

        resposta = QMessageBox.question(
            self,
            "Confirmar",
            f"Atualizar dados LoL draft/compare com:\n{os.path.basename(csv_path)}\n\n"
            "Isso irá substituir os dados antigos. Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if resposta == QMessageBox.StandardButton.Yes:
            self.output_text.clear()
            self.output_text.append("Iniciando atualização...\n")
            self.output_text.append(f"Script: {script_path}\n")
            self.output_text.append(f"CSV: {csv_path}\n\n")

            # Executar script (não-interativo, precisa passar CSV como argumento)
            # O script atualizar_apenas_2026.py aceita o CSV como primeiro argumento e --yes para pular confirmação
            self.update_thread = UpdateThread(script_path, [csv_path, "--yes"], os.path.dirname(script_path))
            self.update_thread.finished.connect(self._on_update_finished)
            self.update_thread.error.connect(self._on_update_error)
            self.update_thread.start()
    
    def _update_dota_prebets(self):
        """Atualiza banco Dota pré-bets."""
        team_id = self.team_id_input.text().strip()
        if not team_id:
            QMessageBox.warning(
                self,
                "Erro",
                "Digite o Team ID do CyberScore."
            )
            return
        
        script_path = r"C:\Users\Lucas\Documents\final\dota_oracle_v1\dota_oracle_v1\import_cyberscore_completo.py"
        if not os.path.exists(script_path):
            QMessageBox.warning(
                self,
                "Erro",
                f"Script não encontrado: {script_path}"
            )
            return
        
        resposta = QMessageBox.question(
            self,
            "Confirmar",
            f"Atualizar banco Dota com Team ID: {team_id}\n\n"
            "Isso pode levar alguns minutos. Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if resposta == QMessageBox.StandardButton.Yes:
            self.output_text.clear()
            self.output_text.append("Iniciando atualização do banco Dota...\n")
            self.output_text.append(f"Script: {script_path}\n")
            self.output_text.append(f"Team ID: {team_id}\n\n")
            
            script_dir = os.path.dirname(script_path)
            # O UpdateThread vai encontrar automaticamente o Python do venv (prioridade) ou do sistema
            self.update_thread = UpdateThread(script_path, [team_id], script_dir)
            self.update_thread.finished.connect(self._on_update_finished)
            self.update_thread.error.connect(self._on_update_error)
            self.update_thread.start()
    
    def _on_update_finished(self, output, success):
        """Chamado quando atualização termina."""
        self.output_text.append("\n" + "="*70 + "\n")
        if success:
            self.output_text.append("[OK] Atualizacao concluida com sucesso!\n")
        else:
            self.output_text.append("[AVISO] Atualizacao concluida com avisos/erros.\n")
        self.output_text.append("="*70 + "\n")
        self.output_text.append(output)
        self.output_text.verticalScrollBar().setValue(
            self.output_text.verticalScrollBar().maximum()
        )
        
        # Verificar se o erro é de módulo faltando
        if not success and "ModuleNotFoundError" in output:
            error_msg = "Erro: Módulo Python não encontrado.\n\n"
            if "selenium" in output.lower():
                error_msg += "O módulo 'selenium' não está instalado no Python usado.\n\n"
                error_msg += "O script está em:\n"
                error_msg += "C:\\Users\\Lucas\\Documents\\final\\dota_oracle_v1\\dota_oracle_v1\\\n\n"
                error_msg += "Soluções:\n"
                error_msg += "1. Instale selenium no venv do projeto Dota:\n"
                error_msg += "   cd C:\\Users\\Lucas\\Documents\\final\\dota_oracle_v1\\dota_oracle_v1\n"
                error_msg += "   .\\venv\\Scripts\\activate\n"
                error_msg += "   pip install selenium\n\n"
                error_msg += "2. Ou instale selenium no venv deste projeto:\n"
                error_msg += "   pip install selenium"
            else:
                error_msg += "Verifique o log acima para mais detalhes."
            QMessageBox.warning(self, "Erro de Dependência", error_msg)
        elif success:
            QMessageBox.information(self, "Sucesso", "Atualização concluída!")
        else:
            QMessageBox.warning(self, "Aviso", "Atualização concluída com avisos. Verifique o log.")
    
    
    def _update_dota_draft(self):
        """Atualiza banco Dota Draft Live executando o fluxo completo."""
        league_id = self.league_id_input.text().strip()
        if not league_id:
            QMessageBox.warning(
                self,
                "Erro",
                "Digite o League ID da OpenDota (ex: 18988)."
            )
            return
        
        try:
            league_id_int = int(league_id)
        except ValueError:
            QMessageBox.warning(
                self,
                "Erro",
                f"League ID inválido: {league_id}\n\nDigite um número válido (ex: 18988)."
            )
            return
        
        league_name = self.league_name_input.text().strip()
        if not league_name:
            league_name = f"OpenDota League {league_id_int}"
        
        api_key = self.api_key_input.text().strip()
        if not api_key:
            resposta = QMessageBox.question(
                self,
                "Aviso",
                "API Key não fornecida. O processo será mais lento devido ao rate limit público.\n\n"
                "Deseja continuar mesmo assim?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if resposta == QMessageBox.StandardButton.No:
                return
        
        dota_dir = TESTEZUDO_DIR if isinstance(TESTEZUDO_DIR, str) else str(TESTEZUDO_DIR)
        if not os.path.exists(dota_dir):
            QMessageBox.warning(
                self,
                "Erro",
                f"Diretório do testezudo não encontrado: {dota_dir}\n\n(É o mesmo que a aba TESTE usa.)"
            )
            return
        
        resposta = QMessageBox.question(
            self,
            "Confirmar",
            f"Atualizar banco e .pkl usados pela aba TESTE (testezudo)?\n\n"
            f"League ID: {league_id_int}\n"
            f"League Name: {league_name}\n"
            f"Diretório: {dota_dir}\n\n"
            f"Isso irá executar:\n"
            f"1. Importar liga {league_id_int} via OpenDota\n"
            f"2. Fazer merge no banco principal\n"
            f"3. Calcular média global\n"
            f"4. Recalcular impactos bayesianos (testezudo)\n\n"
            f"Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if resposta == QMessageBox.StandardButton.Yes:
            self.output_text.clear()
            self.output_text.append("Iniciando atualização (banco + .pkl da aba TESTE)...\n")
            self.output_text.append(f"Diretório: {dota_dir}\n")
            self.output_text.append(f"League ID: {league_id_int}\n")
            self.output_text.append(f"League Name: {league_name}\n")
            self.output_text.append(f"API Key: {'Fornecida' if api_key else 'Não fornecida (usando rate limit público)'}\n\n")
            
            # Executar fluxo completo em sequência
            self._run_dota_draft_flow(league_id_int, league_name, api_key, dota_dir)
    
    def _run_dota_draft_flow(self, league_id, league_name, api_key, dota_dir):
        """Executa o fluxo completo de atualização do Dota Draft."""
        import_script = os.path.join(dota_dir, "import_league_opendota_to_sqlite.py")
        merge_script = os.path.join(dota_dir, "merge_league_into_stratz.py")
        
        # Verificar se os scripts existem
        if not os.path.exists(import_script):
            QMessageBox.warning(
                self,
                "Erro",
                f"Script de importação não encontrado: {import_script}"
            )
            return
        
        if not os.path.exists(merge_script):
            QMessageBox.warning(
                self,
                "Erro",
                f"Script de merge não encontrado: {merge_script}"
            )
            return
        
        # Preparar argumentos do script de importação
        import_args = [str(league_id), league_name]
        if api_key:
            import_args.append(api_key)
        
        scripts = [
            ("1. Importar liga via OpenDota", import_script, import_args),
            ("2. Fazer merge no banco principal", merge_script, [str(league_id)]),
            ("3. Calcular média global", os.path.join(dota_dir, "compute_global_stats_dota_v2.py"), []),
            ("4. Recalcular impactos bayesianos (testezudo / aba TESTE)", os.path.join(dota_dir, "compute_hero_impacts_bayesian_v2_5.py"), []),
        ]
        
        # Executar scripts em sequência
        self._execute_dota_scripts_sequence(scripts, dota_dir, 0)
    
    def _execute_dota_scripts_sequence(self, scripts, dota_dir, index):
        """Executa scripts em sequência."""
        if index >= len(scripts):
            self.output_text.append("\n" + "="*70 + "\n")
            self.output_text.append("[OK] Fluxo completo concluído com sucesso!\n")
            self.output_text.append("="*70 + "\n")
            self.output_text.verticalScrollBar().setValue(
                self.output_text.verticalScrollBar().maximum()
            )
            QMessageBox.information(self, "Sucesso", "Atualização concluída. A aba TESTE usará os novos dados.")
            return
        
        step_name, script_name, args = scripts[index]
        script_path = script_name if os.path.isabs(script_name) else os.path.join(dota_dir, script_name)
        
        if not os.path.exists(script_path):
            self.output_text.append(f"\n[ERRO] Script não encontrado: {script_path}\n")
            QMessageBox.warning(
                self,
                "Erro",
                f"Script não encontrado: {script_path}\n\n"
                f"Passo: {step_name}"
            )
            return
        
        self.output_text.append(f"\n{'='*70}\n")
        self.output_text.append(f"[{step_name}]\n")
        self.output_text.append(f"Script: {os.path.basename(script_path)}\n")
        self.output_text.append(f"Argumentos: {args}\n")
        self.output_text.append(f"Caminho completo: {script_path}\n")
        self.output_text.append(f"{'='*70}\n")
        self.output_text.append("Iniciando execução...\n")
        self.output_text.verticalScrollBar().setValue(
            self.output_text.verticalScrollBar().maximum()
        )
        
        # Passos 3 e 4 (compute): usar DB do testezudo (onde import/merge gravaram)
        extra_env = {"USE_TESTEZUDO_DB": "1"} if index >= 2 else {}
        self.update_thread = UpdateThread(script_path, args, dota_dir, extra_env=extra_env)

        def on_progress(line):
            self.output_text.append(line)
            self.output_text.verticalScrollBar().setValue(
                self.output_text.verticalScrollBar().maximum()
            )
        
        # Conectar sinais para continuar com próximo script após sucesso
        def on_finished(output, success):
            self.output_text.append("\n--- Fim da Execução do Script ---\n")
            self.output_text.verticalScrollBar().setValue(
                self.output_text.verticalScrollBar().maximum()
            )
            
            if success:
                self.output_text.append(f"\n✅ Passo '{step_name}' concluído com sucesso!\n")
                # Continuar com próximo script
                self._execute_dota_scripts_sequence(scripts, dota_dir, index + 1)
            else:
                self.output_text.append(f"\n❌ Falha no passo: {step_name}\n")
                QMessageBox.warning(
                    self,
                    "Erro",
                    f"Falha no passo: {step_name}\n\n"
                    f"Verifique o log para mais detalhes."
                )
        
        def on_error(error_msg):
            self.output_text.append(f"\n[ERRO CRÍTICO] {error_msg}\n")
            self.output_text.verticalScrollBar().setValue(
                self.output_text.verticalScrollBar().maximum()
            )
            QMessageBox.critical(
                self,
                "Erro Crítico",
                f"Erro ao executar passo '{step_name}':\n\n{error_msg}"
            )
        
        self.update_thread.progress.connect(on_progress)
        self.update_thread.finished.connect(on_finished)
        self.update_thread.error.connect(on_error)
        self.update_thread.start()
        
        self.output_text.append("Thread iniciada, aguardando execução...\n")
        self.output_text.verticalScrollBar().setValue(
            self.output_text.verticalScrollBar().maximum()
        )
    
    def _on_update_error(self, error_msg):
        """Chamado quando há erro na atualização."""
        self.output_text.append(f"\n[ERRO] ERRO: {error_msg}\n")
        QMessageBox.critical(self, "Erro", f"Erro ao executar atualização:\n{error_msg}")
