"""
Página de Pré-bets do LoL.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QGroupBox, QFormLayout,
    QDoubleSpinBox, QMessageBox
)
from PySide6.QtCore import Qt, QThread, Signal
from core.lol.prebets import LoLPrebetsAnalyzer
from core.shared.db import save_bet


class AnalysisThread(QThread):
    """Thread para executar análise sem travar a UI."""
    finished = Signal(dict)
    error = Signal(str)
    
    def __init__(self, analyzer, market_type, team1, team2, odd, league):
        super().__init__()
        self.analyzer = analyzer
        self.market_type = market_type
        self.team1 = team1
        self.team2 = team2
        self.odd = odd
        self.league = league
    
    def run(self):
        try:
            result = self.analyzer.analyze_bet(
                self.market_type,
                self.team1,
                self.team2,
                odd=self.odd,
                league=self.league
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class LoLPrebetsPage(QWidget):
    """Página de análise de pré-bets do LoL."""
    
    def __init__(self):
        super().__init__()
        self.analyzer = LoLPrebetsAnalyzer()
        self.analysis_thread = None
        
        self._init_ui()
        self._load_data()
    
    def _init_ui(self):
        """Inicializa a interface."""
        layout = QVBoxLayout(self)
        
        # Grupo de seleção
        selection_group = QGroupBox("Seleção de Jogo")
        selection_layout = QFormLayout()
        
        # Liga
        self.league_combo = QComboBox()
        self.league_combo.setEditable(False)
        selection_layout.addRow("Liga:", self.league_combo)
        
        # Time 1
        self.team1_combo = QComboBox()
        self.team1_combo.setEditable(True)
        selection_layout.addRow("Time 1:", self.team1_combo)
        
        # Time 2
        self.team2_combo = QComboBox()
        self.team2_combo.setEditable(True)
        selection_layout.addRow("Time 2:", self.team2_combo)
        
        selection_group.setLayout(selection_layout)
        layout.addWidget(selection_group)
        
        # Grupo de aposta
        bet_group = QGroupBox("Dados da Aposta")
        bet_layout = QFormLayout()
        
        # Odd
        self.odd_spin = QDoubleSpinBox()
        self.odd_spin.setMinimum(1.01)
        self.odd_spin.setMaximum(100.0)
        self.odd_spin.setDecimals(2)
        self.odd_spin.setValue(2.0)
        bet_layout.addRow("Odd:", self.odd_spin)
        
        bet_group.setLayout(bet_layout)
        layout.addWidget(bet_group)
        
        # Botão de calcular
        self.calculate_btn = QPushButton("Calcular")
        self.calculate_btn.clicked.connect(self._calculate)
        layout.addWidget(self.calculate_btn)
        
        # Tabela de resultados
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(5)
        self.results_table.setHorizontalHeaderLabels([
            "Time", "Probabilidade", "Fair Odd", "EV", "Ação"
        ])
        layout.addWidget(self.results_table)
        
        # Botão de salvar aposta
        self.save_btn = QPushButton("Salvar no Histórico")
        self.save_btn.clicked.connect(self._save_bet)
        self.save_btn.setEnabled(False)
        layout.addWidget(self.save_btn)
        
        # Conectar mudanças de liga para atualizar times
        self.league_combo.currentTextChanged.connect(self._update_teams)
    
    def _load_data(self):
        """Carrega dados disponíveis."""
        if not self.analyzer.load_data():
            QMessageBox.warning(self, "Erro", "Não foi possível carregar os dados.")
            return
        
        # Carregar ligas
        leagues = self.analyzer.get_available_leagues()
        self.league_combo.addItems([""] + leagues)
        
        # Atualizar times
        self._update_teams()
    
    def _update_teams(self):
        """Atualiza lista de times baseado na liga selecionada."""
        league = self.league_combo.currentText()
        if not league:
            league = None
        
        teams = self.analyzer.get_available_teams(league)
        
        self.team1_combo.clear()
        self.team1_combo.addItems([""] + teams)
        
        self.team2_combo.clear()
        self.team2_combo.addItems([""] + teams)
    
    def _calculate(self):
        """Calcula análise da aposta."""
        team1 = self.team1_combo.currentText().strip()
        team2 = self.team2_combo.currentText().strip()
        league = self.league_combo.currentText().strip() or None
        odd = self.odd_spin.value()
        
        if not team1 or not team2:
            QMessageBox.warning(self, "Erro", "Selecione ambos os times.")
            return
        
        if team1 == team2:
            QMessageBox.warning(self, "Erro", "Os times devem ser diferentes.")
            return
        
        # Desabilitar botão durante cálculo
        self.calculate_btn.setEnabled(False)
        self.calculate_btn.setText("Calculando...")
        
        # Executar em thread separada
        self.analysis_thread = AnalysisThread(
            self.analyzer, "Map Winner", team1, team2, odd, league
        )
        self.analysis_thread.finished.connect(self._on_analysis_finished)
        self.analysis_thread.error.connect(self._on_analysis_error)
        self.analysis_thread.start()
    
    def _on_analysis_finished(self, result):
        """Chamado quando análise termina."""
        self.calculate_btn.setEnabled(True)
        self.calculate_btn.setText("Calcular")
        
        if result is None:
            QMessageBox.warning(self, "Erro", "Não foi possível calcular a análise.")
            return
        
        # Preencher tabela
        self.results_table.setRowCount(2)
        
        # Time 1
        self.results_table.setItem(0, 0, QTableWidgetItem(result["team1"]))
        self.results_table.setItem(0, 1, QTableWidgetItem(f"{result['probability_team1']*100:.2f}%"))
        self.results_table.setItem(0, 2, QTableWidgetItem(f"{result['fair_odd_team1']:.2f}"))
        ev1 = result.get("ev_team1", 0)
        ev_item1 = QTableWidgetItem(f"{ev1:.2f}%")
        if ev1 > 0:
            ev_item1.setForeground(Qt.GlobalColor.green)
        elif ev1 < 0:
            ev_item1.setForeground(Qt.GlobalColor.red)
        self.results_table.setItem(0, 3, ev_item1)
        action1 = "APOSTAR" if ev1 > 0 else "EVITAR"
        self.results_table.setItem(0, 4, QTableWidgetItem(action1))
        
        # Time 2
        self.results_table.setItem(1, 0, QTableWidgetItem(result["team2"]))
        self.results_table.setItem(1, 1, QTableWidgetItem(f"{result['probability_team2']*100:.2f}%"))
        self.results_table.setItem(1, 2, QTableWidgetItem(f"{result['fair_odd_team2']:.2f}"))
        ev2 = result.get("ev_team2", 0)
        ev_item2 = QTableWidgetItem(f"{ev2:.2f}%")
        if ev2 > 0:
            ev_item2.setForeground(Qt.GlobalColor.green)
        elif ev2 < 0:
            ev_item2.setForeground(Qt.GlobalColor.red)
        self.results_table.setItem(1, 3, ev_item2)
        action2 = "APOSTAR" if ev2 > 0 else "EVITAR"
        self.results_table.setItem(1, 4, QTableWidgetItem(action2))
        
        # Ajustar colunas
        self.results_table.resizeColumnsToContents()
        
        # Habilitar botão de salvar
        self.save_btn.setEnabled(True)
        self._last_result = result
    
    def _on_analysis_error(self, error_msg):
        """Chamado quando há erro na análise."""
        self.calculate_btn.setEnabled(True)
        self.calculate_btn.setText("Calcular")
        QMessageBox.critical(self, "Erro", f"Erro ao calcular: {error_msg}")
    
    def _save_bet(self):
        """Salva aposta no histórico."""
        if not hasattr(self, '_last_result'):
            return
        
        result = self._last_result
        
        # Determinar qual time tem melhor EV
        ev1 = result.get("ev_team1", 0)
        ev2 = result.get("ev_team2", 0)
        
        if ev1 > ev2:
            choice = result["team1"]
            prob = result["probability_team1"]
            ev = ev1
        else:
            choice = result["team2"]
            prob = result["probability_team2"]
            ev = ev2
        
        from core.shared.db import save_bet
        save_bet(
            game="LoL",
            league=self.league_combo.currentText() or None,
            market="Map Winner",
            line=None,
            odd=self.odd_spin.value(),
            probability=prob,
            ev=ev,
            choice=choice
        )
        
        QMessageBox.information(self, "Sucesso", "Aposta salva no histórico!")
