"""
Página de Draft Live do LoL.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QTableWidget, QTableWidgetItem, QGroupBox, QFormLayout,
    QDoubleSpinBox, QMessageBox, QTextEdit, QCompleter,
)
from PySide6.QtCore import Qt, QThread, Signal
from core.lol.draft import LoLDraftAnalyzer


class DraftAnalysisThread(QThread):
    """Thread para executar análise de draft sem travar a UI."""
    finished = Signal(dict)
    error = Signal(str)
    
    def __init__(self, analyzer, league, team1, team2, threshold):
        super().__init__()
        self.analyzer = analyzer
        self.league = league
        self.team1 = team1
        self.team2 = team2
        self.threshold = threshold
    
    def run(self):
        try:
            result = self.analyzer.analyze_draft(
                self.league,
                self.team1,
                self.team2,
                self.threshold
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class LoLDraftPage(QWidget):
    """Página de análise de draft do LoL."""
    
    def __init__(self):
        super().__init__()
        self.analyzer = LoLDraftAnalyzer()
        self.analysis_thread = None
        
        self._init_ui()
        self._load_data()
    
    def _init_ui(self):
        """Inicializa a interface."""
        layout = QVBoxLayout(self)
        
        # Grupo de seleção
        selection_group = QGroupBox("Configuração do Draft")
        selection_layout = QFormLayout()
        
        # Liga
        self.league_combo = QComboBox()
        self.league_combo.setEditable(True)  # Permitir edição para digitar liga
        self.league_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)  # Não adicionar duplicatas
        selection_layout.addRow("Liga:", self.league_combo)
        
        # Threshold
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setMinimum(0.50)
        self.threshold_spin.setMaximum(0.99)
        self.threshold_spin.setDecimals(2)
        self.threshold_spin.setSingleStep(0.01)
        self.threshold_spin.setValue(0.55)
        selection_layout.addRow("Threshold:", self.threshold_spin)
        
        selection_group.setLayout(selection_layout)
        layout.addWidget(selection_group)
        
        # Times
        teams_layout = QHBoxLayout()
        
        # Time 1
        team1_group = QGroupBox("Time 1 (Blue Side)")
        team1_layout = QFormLayout()
        
        self.team1_picks = []
        for i in range(5):
            pick = QComboBox()
            pick.setEditable(True)
            pick.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            pick.lineEdit().setPlaceholderText(f"Campeão {i+1}")
            self.team1_picks.append(pick)
            team1_layout.addRow(f"Pick {i+1}:", pick)
        
        team1_group.setLayout(team1_layout)
        teams_layout.addWidget(team1_group)
        
        # Time 2
        team2_group = QGroupBox("Time 2 (Red Side)")
        team2_layout = QFormLayout()
        
        self.team2_picks = []
        for i in range(5):
            pick = QComboBox()
            pick.setEditable(True)
            pick.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            pick.lineEdit().setPlaceholderText(f"Campeão {i+1}")
            self.team2_picks.append(pick)
            team2_layout.addRow(f"Pick {i+1}:", pick)
        
        team2_group.setLayout(team2_layout)
        teams_layout.addWidget(team2_group)
        
        layout.addLayout(teams_layout)
        
        # Botão de calcular
        self.calculate_btn = QPushButton("Analisar Draft")
        self.calculate_btn.clicked.connect(self._calculate)
        layout.addWidget(self.calculate_btn)
        
        # Resultados
        results_layout = QHBoxLayout()
        
        # Tabela de linhas
        self.lines_table = QTableWidget()
        self.lines_table.setColumnCount(4)
        self.lines_table.setHorizontalHeaderLabels([
            "Linha", "Prob(UNDER)", "Prob(OVER)", "Recomendação"
        ])
        results_layout.addWidget(self.lines_table)
        
        # Área de detalhes
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        results_layout.addWidget(self.details_text)
        
        layout.addLayout(results_layout)

    def _populate_champion_picks(self):
        """Lista de campeões + QCompleter (igual ideia ao Dota Draft: combo editável com sugestões)."""
        from core.lol.oracle_team_games import load_draft_champion_name_list

        try:
            champs = load_draft_champion_name_list()
        except Exception:
            champs = []

        for side in (self.team1_picks, self.team2_picks):
            for i, pick in enumerate(side):
                pick.clear()
                pick.addItems([""] + champs)
                pick.lineEdit().setPlaceholderText(f"Campeão {i + 1}")
                comp = QCompleter(champs)
                comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
                comp.setFilterMode(Qt.MatchFlag.MatchContains)
                comp.setMaxVisibleItems(20)
                pick.lineEdit().setCompleter(comp)

    def _load_data(self):
        """Carrega dados disponíveis."""
        try:
            if not self.analyzer.load_models():
                # Mostrar mensagem de erro mais detalhada
                import sys
                import os
                import traceback
                from core.shared.paths import BASE_DIR, get_data_dir, get_models_dir
                
                exe_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else BASE_DIR
                data_dir = get_data_dir()
                models_dir = get_models_dir()
                
                # Verificar se os arquivos existem
                files_exist = {
                    "champion_impacts.csv": os.path.exists(os.path.join(data_dir, "champion_impacts.csv")),
                    "league_stats_v3.pkl": os.path.exists(os.path.join(data_dir, "league_stats_v3.pkl")),
                    "trained_models_v3.pkl": os.path.exists(os.path.join(models_dir, "trained_models_v3.pkl")),
                    "scaler_v3.pkl": os.path.exists(os.path.join(models_dir, "scaler_v3.pkl")),
                    "feature_columns_v3.pkl": os.path.exists(os.path.join(models_dir, "feature_columns_v3.pkl")),
                }
                
                files_status = "\n".join([f"- {name}: {'[OK]' if exists else '[X]'}" for name, exists in files_exist.items()])
                
                error_msg = f"""Não foi possível carregar os modelos.

Verifique se os arquivos estão presentes:
- Data: {data_dir}
- Models: {models_dir}

Diretório do executável: {exe_dir}

Status dos arquivos:
{files_status}

Se todos os arquivos existem ([OK]), o problema pode ser:
- Erro ao importar scipy/sklearn
- Modelos corrompidos
- Versão incompatível de bibliotecas

Verifique o console para mais detalhes do erro."""
                
                QMessageBox.warning(self, "Erro", error_msg)
                return

            # Carregar ligas
            leagues = self.analyzer.get_available_leagues()
            if leagues:
                self.league_combo.addItems(leagues)
                self.league_combo.setCurrentIndex(0)  # Selecionar primeira liga
            else:
                # Se não houver ligas, adicionar algumas comuns manualmente
                default_leagues = ["LCK", "LPL", "LEC", "LCS", "CBLOL", "LCP"]
                self.league_combo.addItems(default_leagues)
                QMessageBox.information(self, "Aviso", "Ligas padrão carregadas. Se não funcionar, verifique os dados.")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao carregar dados: {str(e)}")
            # Adicionar ligas padrão mesmo em caso de erro
            default_leagues = ["LCK", "LPL", "LEC", "LCS", "CBLOL", "LCP"]
            self.league_combo.addItems(default_leagues)
        finally:
            self._populate_champion_picks()
    
    def _calculate(self):
        """Calcula análise do draft."""
        league = self.league_combo.currentText().strip()
        if not league:
            QMessageBox.warning(self, "Erro", "Selecione uma liga.")
            return
        
        # Coletar picks (QComboBox editável: mesmo padrão do Dota Draft)
        team1 = [p.currentText().strip() for p in self.team1_picks if p.currentText().strip()]
        team2 = [p.currentText().strip() for p in self.team2_picks if p.currentText().strip()]
        
        if len(team1) != 5:
            QMessageBox.warning(self, "Erro", "Time 1 deve ter exatamente 5 campeões.")
            return
        
        if len(team2) != 5:
            QMessageBox.warning(self, "Erro", "Time 2 deve ter exatamente 5 campeões.")
            return
        
        threshold = self.threshold_spin.value()
        
        # Desabilitar botão durante cálculo
        self.calculate_btn.setEnabled(False)
        self.calculate_btn.setText("Calculando...")
        
        # Executar em thread separada
        self.analysis_thread = DraftAnalysisThread(
            self.analyzer, league, team1, team2, threshold
        )
        self.analysis_thread.finished.connect(self._on_analysis_finished)
        self.analysis_thread.error.connect(self._on_analysis_error)
        self.analysis_thread.start()
    
    def _on_analysis_finished(self, result):
        """Chamado quando análise termina."""
        self.calculate_btn.setEnabled(True)
        self.calculate_btn.setText("Analisar Draft")
        
        if result is None:
            QMessageBox.warning(self, "Erro", "Não foi possível calcular a análise.")
            return
        
        # Preencher tabela de linhas
        resultados = result.get("resultados", {})
        self.lines_table.setRowCount(len(resultados))
        
        for row, (line, r) in enumerate(sorted(resultados.items(), key=lambda kv: float(kv[0]))):
            self.lines_table.setItem(row, 0, QTableWidgetItem(str(line)))
            self.lines_table.setItem(row, 1, QTableWidgetItem(f"{r['Prob(UNDER)']:.2f}%"))
            self.lines_table.setItem(row, 2, QTableWidgetItem(f"{r['Prob(OVER)']:.2f}%"))
            
            choice = r.get("Escolha", "N/A")
            conf = r.get("Confiança", "N/A")
            rec_item = QTableWidgetItem(f"{choice} ({conf})")
            if conf == "High":
                rec_item.setForeground(Qt.GlobalColor.green)
            elif conf == "Low":
                rec_item.setForeground(Qt.GlobalColor.red)
            self.lines_table.setItem(row, 3, rec_item)
        
        self.lines_table.resizeColumnsToContents()
        
        # Preencher detalhes
        details = []
        details.append("=== IMPACTOS INDIVIDUAIS ===\n")
        
        # Impactos individuais
        impactos = result.get("impactos_individuais", {})
        if impactos:
            for label, team_label in [("team1", "Time 1"), ("team2", "Time 2")]:
                if impactos.get(label):
                    details.append(f"{team_label}:\n")
                    for imp_data in impactos[label]:
                        champ = imp_data["champion"]
                        imp = imp_data["impact"]
                        n_games = imp_data["n_games"]
                        details.append(f"  {champ:<12} {imp:+.2f} (n={n_games})\n")
                    details.append("\n")
        
        details.append("=== ANÁLISE DE DRAFT ===\n")
        details.append(f"Liga: {result.get('league', 'N/A')}\n")
        details.append(f"Kills Estimados: {result.get('kills_estimados', 0):.2f}\n")
        details.append(f"Impacto Time 1: {result.get('impacto_t1', 0):+.2f}\n")
        details.append(f"Impacto Time 2: {result.get('impacto_t2', 0):+.2f}\n\n")
        
        # Sinergias
        sinergias = result.get("sinergias", {})
        if sinergias.get("team1") or sinergias.get("team2"):
            details.append("=== SINERGIAS ===\n")
            if sinergias.get("team1"):
                details.append("Time 1:\n")
                for s in sinergias["team1"]:
                    details.append(f"  {s['champ1']} + {s['champ2']}: {s['sinergia']:+.2f} kills (n={s['n_games']})\n")
            if sinergias.get("team2"):
                details.append("Time 2:\n")
                for s in sinergias["team2"]:
                    details.append(f"  {s['champ1']} + {s['champ2']}: {s['sinergia']:+.2f} kills (n={s['n_games']})\n")
            details.append("\n")
        
        # Matchups
        matchups = result.get("matchups", {})
        if isinstance(matchups, dict):
            # Novo formato com diretos e anyrole
            matchups_diretos = matchups.get("diretos", [])
            matchups_anyrole = matchups.get("anyrole", [])
            
            if matchups_diretos or matchups_anyrole:
                details.append("=== MATCHUPS ===\n")
                
                # Matchups diretos (por role)
                for m in matchups_diretos:
                    details.append(f"{m['role'].upper()}: {m['champ1']} vs {m['champ2']} → {m['impacto']:+.2f} kills (n={m['n_games']})\n")
                
                # Anyrole matchups
                if matchups_anyrole:
                    details.append("\nAnyrole matchups (fora das lanes diretas):\n")
                    for m in matchups_anyrole:
                        details.append(f"  - {m['champ1']} vs {m['champ2']} → {m['impacto']:+.2f} kills (n={m['n_games']})\n")
        elif isinstance(matchups, list):
            # Formato antigo (compatibilidade)
            if matchups:
                details.append("=== MATCHUPS ===\n")
                for m in matchups:
                    details.append(f"{m['role'].upper()}: {m['champ1']} vs {m['champ2']} → {m['impacto']:+.2f} kills (n={m['n_games']})\n")
        
        self.details_text.setPlainText("".join(details))
    
    def _on_analysis_error(self, error_msg):
        """Chamado quando há erro na análise."""
        self.calculate_btn.setEnabled(True)
        self.calculate_btn.setText("Analisar Draft")
        QMessageBox.critical(self, "Erro", f"Erro ao calcular: {error_msg}")
