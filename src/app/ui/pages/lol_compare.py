"""
Página de Comparação de Composições do LoL.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QLineEdit, QGroupBox, QFormLayout, QMessageBox, QTextEdit, QScrollArea
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QTextCursor
from core.lol.compare import LoLCompareAnalyzer


class CompareAnalysisThread(QThread):
    """Thread para executar análise de comparação sem travar a UI."""
    finished = Signal(dict)
    error = Signal(str)
    
    def __init__(self, analyzer, league, comp1, comp2):
        super().__init__()
        self.analyzer = analyzer
        self.league = league
        self.comp1 = comp1
        self.comp2 = comp2
    
    def run(self):
        try:
            result = self.analyzer.compare_compositions(
                self.league,
                self.comp1,
                self.comp2
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class CalibrateDraftPriorThread(QThread):
    finished = Signal(dict)
    error = Signal(str)

    def run(self):
        try:
            from core.lol.draft_prior import train_calibrator
            from core.lol.compare import LoLCompareAnalyzer
            analyzer = LoLCompareAnalyzer()
            analyzer.load_data()
            metrics = train_calibrator(analyzer=analyzer)
            self.finished.emit(metrics)
        except Exception as e:
            self.error.emit(str(e))


class LoLComparePage(QWidget):
    """Página de comparação de composições do LoL."""
    
    def __init__(self):
        super().__init__()
        self.analyzer = LoLCompareAnalyzer()
        self.analysis_thread = None
        self.calibrate_thread = None
        
        self._init_ui()
        self._load_data()
    
    def _init_ui(self):
        """Inicializa a interface do usuário."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # Título
        title = QLabel("Comparação de Composições")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        
        # Configuração
        config_group = QGroupBox("Configuração")
        config_layout = QFormLayout()
        
        self.league_combo = QComboBox()
        self.league_combo.setEditable(True)
        config_layout.addRow("Liga:", self.league_combo)
        
        config_group.setLayout(config_layout)
        layout.addWidget(config_group)
        
        # Time 1
        team1_group = QGroupBox("Time 1")
        team1_layout = QFormLayout()
        
        self.team1_picks = []
        positions = ["Top", "Jungle", "Mid", "ADC", "Support"]
        for pos in positions:
            pick = QLineEdit()
            pick.setPlaceholderText(f"{pos}...")
            team1_layout.addRow(f"{pos}:", pick)
            self.team1_picks.append(pick)
        
        team1_group.setLayout(team1_layout)
        layout.addWidget(team1_group)
        
        # Time 2
        team2_group = QGroupBox("Time 2")
        team2_layout = QFormLayout()
        
        self.team2_picks = []
        for pos in positions:
            pick = QLineEdit()
            pick.setPlaceholderText(f"{pos}...")
            team2_layout.addRow(f"{pos}:", pick)
            self.team2_picks.append(pick)
        
        team2_group.setLayout(team2_layout)
        layout.addWidget(team2_group)
        
        # Botões: comparar
        btn_layout = QHBoxLayout()
        self.compare_btn = QPushButton("Comparar Composições")
        self.compare_btn.clicked.connect(self._on_compare_clicked)
        btn_layout.addWidget(self.compare_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        # ---- Calibração (transformar score em prob real) ----
        cal_group = QGroupBox("Calibração (transformar score em prob real)")
        cal_layout = QVBoxLayout()
        cal_desc = QLabel(
            "No histórico calculamos draft_delta = score_time1 − score_time2 e treinamos uma "
            "regressão logística: p_draft = σ(a·draft_delta + b). Assim 60% passa a significar ~60% de chance real."
        )
        cal_desc.setWordWrap(True)
        cal_desc.setStyleSheet("color: #444; font-size: 12px;")
        cal_layout.addWidget(cal_desc)
        cal_btn_row = QHBoxLayout()
        self.calibrate_btn = QPushButton("Treinar calibrador (σ(a·Δ+b))")
        self.calibrate_btn.setToolTip("Treina no histórico: draft_delta → vitória. Use uma vez; depois as comparações exibem Prob. calibrada.")
        self.calibrate_btn.clicked.connect(self._on_calibrate_clicked)
        cal_btn_row.addWidget(self.calibrate_btn)
        self.calibrate_status_label = QLabel("")
        self.calibrate_status_label.setStyleSheet("color: gray; font-size: 11px;")
        cal_btn_row.addWidget(self.calibrate_status_label)
        cal_btn_row.addStretch()
        cal_layout.addLayout(cal_btn_row)
        cal_group.setLayout(cal_layout)
        layout.addWidget(cal_group)
        self._update_calibrate_status()
        
        # Área de resultados (scrollável)
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setFontFamily("Consolas")
        self.results_text.setMinimumHeight(400)
        # Garantir que o texto seja exibido completamente
        self.results_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        
        layout.addWidget(self.results_text)
    
    def _update_calibrate_status(self):
        """Atualiza o rótulo de status do calibrador (Calibrado / Não calibrado)."""
        try:
            from core.lol.draft_prior import load_calibrator
            model, _ = load_calibrator()
            if model is not None:
                self.calibrate_status_label.setText("✓ Calibrado — comparações exibem prob. real.")
            else:
                self.calibrate_status_label.setText("Não calibrado — clique em 'Treinar calibrador'.")
        except Exception:
            self.calibrate_status_label.setText("")

    def _load_data(self):
        """Carrega dados e popula combos."""
        try:
            if not self.analyzer.load_data():
                QMessageBox.warning(self, "Aviso", "Não foi possível carregar os dados.")
                return
            
            self._update_calibrate_status()
            leagues = self.analyzer.get_available_leagues()
            if leagues:
                self.league_combo.addItems(leagues)
                # Definir "MAJOR" como padrão se existir
                if "MAJOR" in leagues:
                    self.league_combo.setCurrentText("MAJOR")
            else:
                # Fallback: adicionar ligas major padrão
                default_leagues = ["MAJOR", "LCK", "LPL", "LCS", "LEC", "CBLOL", "LCP"]
                self.league_combo.addItems(default_leagues)
                self.league_combo.setCurrentText("MAJOR")
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Erro ao carregar dados: {e}")
    
    def _on_compare_clicked(self):
        """Chamado quando o botão de comparar é clicado."""
        # Validar entradas
        league = self.league_combo.currentText().strip()
        if not league:
            QMessageBox.warning(self, "Erro", "Selecione uma liga.")
            return
        
        comp1 = []
        comp2 = []
        
        for pick in self.team1_picks:
            champ = pick.text().strip()
            if not champ:
                QMessageBox.warning(self, "Erro", "Preencha todos os campeões do Time 1.")
                return
            comp1.append(champ)
        
        for pick in self.team2_picks:
            champ = pick.text().strip()
            if not champ:
                QMessageBox.warning(self, "Erro", "Preencha todos os campeões do Time 2.")
                return
            comp2.append(champ)
        
        # Desabilitar botão durante análise
        self.compare_btn.setEnabled(False)
        self.compare_btn.setText("Comparando...")
        
        # Executar análise em thread separada
        self.analysis_thread = CompareAnalysisThread(
            self.analyzer,
            league,
            comp1,
            comp2
        )
        self.analysis_thread.finished.connect(self._on_analysis_finished)
        self.analysis_thread.error.connect(self._on_analysis_error)
        self.analysis_thread.start()
    
    def _on_analysis_finished(self, result):
        """Chamado quando análise termina."""
        self.compare_btn.setEnabled(True)
        self.compare_btn.setText("Comparar Composições")
        
        if result is None:
            QMessageBox.warning(self, "Erro", "Não foi possível realizar a comparação.")
            return
        
        # Formatar resultado para exibição
        output = []
        output.append("=" * 60)
        output.append("COMPARAÇÃO DE COMPOSIÇÕES")
        output.append("=" * 60)
        output.append("")
        
        # Liga
        league_display = result.get("league", "N/A")
        if isinstance(league_display, list):
            # Verificar se são todas as 6 ligas major (incluindo LCS)
            ordem_major = ["LCK", "LPL", "LCS", "CBLOL", "LCP", "LEC"]
            if len(league_display) == 6 and set(league_display) == set(ordem_major):
                league_display = "MAJOR (todas)"
            else:
                league_display = ", ".join(league_display)
        output.append(f"Liga(s): {league_display}")
        output.append("")
        output.append(f"Time 1: {' + '.join(result.get('comp1', []))}")
        output.append(f"Time 2: {' + '.join(result.get('comp2', []))}")
        output.append("")
        
        # Análise Time 1
        factors1 = result.get("factors1", {})
        output.append("-" * 60)
        output.append("ANÁLISE TIME 1:")
        output.append("-" * 60)
        
        output.append("   Win Rates Individuais dos Campeões:")
        for champ_detail in factors1.get("champ_details", []):
            games = champ_detail.get("games", 0)
            if games > 0:
                output.append(f"      {champ_detail['champion']}: {champ_detail['win_rate']:.2f}% ({games} jogos)")
            else:
                output.append(f"      {champ_detail['champion']}: {champ_detail['win_rate']:.2f}% (sem dados)")
        
        output.append(f"   Win Rate médio dos campeões: {factors1.get('avg_champ_wr', 0):.2f}%")
        output.append("      [Média simples dos win rates individuais acima]")
        
        output.append("")
        output.append("   Sinergias (Pares de Campeões):")
        sinergias_com_dados = [s for s in factors1.get("synergy_details", []) if s.get("games", 0) > 0]
        if sinergias_com_dados:
            for syn_detail in sinergias_com_dados:
                output.append(f"      {syn_detail['champ1']} + {syn_detail['champ2']}: {syn_detail['win_rate']:.2f}% WR ({syn_detail['games']} jogos) | Impacto: {syn_detail['impact']:+.2f}%")
            output.append(f"   Impacto médio de sinergias: {factors1.get('avg_synergy_impact', 0):+.2f}%")
            output.append("      [Média dos impactos acima | Positivo = jogam bem juntos | Negativo = não combinam bem]")
        else:
            output.append("      [AVISO] Nenhuma sinergia com dados suficientes (mínimo 5 jogos)")
            output.append(f"   Impacto médio de sinergias: {factors1.get('avg_synergy_impact', 0):+.2f}%")
        
        comp_wr1 = factors1.get("comp_wr")
        if comp_wr1:
            output.append("")
            output.append(f"   Win Rate da composição completa: {comp_wr1:.2f}% ({factors1.get('comp_games', 0)} jogos)")
        else:
            output.append("")
            output.append("   Win Rate da composição completa: N/A (composição não encontrada no histórico)")
        
        output.append("")
        output.append(f"   Score Total: {factors1.get('total_score', 0):.2f}%")
        
        # Análise Time 2
        factors2 = result.get("factors2", {})
        output.append("")
        output.append("-" * 60)
        output.append("ANÁLISE TIME 2:")
        output.append("-" * 60)
        
        output.append("   Win Rates Individuais dos Campeões:")
        for champ_detail in factors2.get("champ_details", []):
            games = champ_detail.get("games", 0)
            if games > 0:
                output.append(f"      {champ_detail['champion']}: {champ_detail['win_rate']:.2f}% ({games} jogos)")
            else:
                output.append(f"      {champ_detail['champion']}: {champ_detail['win_rate']:.2f}% (sem dados)")
        
        output.append(f"   Win Rate médio dos campeões: {factors2.get('avg_champ_wr', 0):.2f}%")
        output.append("      [Média simples dos win rates individuais acima]")
        
        output.append("")
        output.append("   Sinergias (Pares de Campeões):")
        sinergias_com_dados = [s for s in factors2.get("synergy_details", []) if s.get("games", 0) > 0]
        if sinergias_com_dados:
            for syn_detail in sinergias_com_dados:
                output.append(f"      {syn_detail['champ1']} + {syn_detail['champ2']}: {syn_detail['win_rate']:.2f}% WR ({syn_detail['games']} jogos) | Impacto: {syn_detail['impact']:+.2f}%")
            output.append(f"   Impacto médio de sinergias: {factors2.get('avg_synergy_impact', 0):+.2f}%")
            output.append("      [Média dos impactos acima | Positivo = jogam bem juntos | Negativo = não combinam bem]")
        else:
            output.append("      [AVISO] Nenhuma sinergia com dados suficientes (mínimo 5 jogos)")
            output.append(f"   Impacto médio de sinergias: {factors2.get('avg_synergy_impact', 0):+.2f}%")
        
        comp_wr2 = factors2.get("comp_wr")
        if comp_wr2:
            output.append("")
            output.append(f"   Win Rate da composição completa: {comp_wr2:.2f}% ({factors2.get('comp_games', 0)} jogos)")
        else:
            output.append("")
            output.append("   Win Rate da composição completa: N/A (composição não encontrada no histórico)")
        
        output.append("")
        output.append(f"   Score Total: {factors2.get('total_score', 0):.2f}%")
        
        # Resultado
        output.append("")
        output.append("=" * 60)
        output.append("RESULTADO:")
        output.append("=" * 60)
        output.append(f"   Vencedor Previsto: {result.get('winner', 'N/A')}")
        output.append(f"   Diferença: {result.get('difference', 0):.2f}% pontos")
        
        diff = result.get("difference", 0)
        if diff < 2:
            output.append("   [AVISO] Partida muito equilibrada!")
        elif diff < 5:
            output.append("   [INFO] Partida equilibrada, mas com leve vantagem")
        else:
            output.append("   [OK] Vantagem significativa")

        p_draft = result.get("p_draft_calibrated")
        if p_draft is not None:
            p_draft_t2 = 1.0 - p_draft
            output.append("")
            output.append("   --- Prob. calibrada (p_draft = σ(a·Δ+b)) ---")
            output.append(f"   Prob. calibrada (Time 1): {p_draft*100:.1f}%  (60% ≈ 60% de chance real)")
            output.append(f"   Prob. calibrada (Time 2): {p_draft_t2*100:.1f}%")
            output.append("   [Use na aba 'Prob. de Vitória' ou Early/Full-Game; prior é preenchido automaticamente]")
            # Guardar para auto-preenchimento nas abas Early-Game e Full-Game
            mw = self.window()
            if mw is not None and hasattr(mw, "app_state"):
                mw.app_state["draft_prior_pct"] = round(p_draft * 100, 1)
        
        # Matchups individuais
        output.append("")
        output.append("-" * 60)
        output.append("MATCHUPS INDIVIDUAIS (Time 1 vs Time 2):")
        output.append("[INFO] Win Rate = porcentagem de vitórias do campeão do Time 1 quando enfrenta o campeão do Time 2")
        output.append("[INFO] Apenas matchups com 5 ou mais jogos são exibidos")
        output.append("-" * 60)
        
        matchup_details = result.get("matchup_details", [])
        matchups_exibidos = 0
        for matchup in matchup_details:
            if matchup.get("games", 0) > 0:
                output.append(f"   {matchup['champ1']} ({matchup['pos1']}) vs {matchup['champ2']} ({matchup['pos2']}): {matchup['win_rate']:.2f}% WR de {matchup['champ1']} ({matchup['games']} jogos)")
                matchups_exibidos += 1
        
        avg_matchup = result.get("avg_matchup_wr", 0)
        if matchups_exibidos > 0:
            output.append("")
            output.append(f"   Win Rate médio nos matchups (do Time 1): {avg_matchup:.2f}%")
            output.append(f"   Matchups exibidos: {matchups_exibidos}/25 ({matchups_exibidos*100//25}%)")
        else:
            output.append("")
            output.append("   [AVISO] Nenhum matchup com dados suficientes (mínimo 5 jogos)")
        
        # Adicionar linha final (igual ao PowerShell)
        output.append("")
        output.append("=" * 60)
        output.append("[OK] Análise concluída!")
        output.append("=" * 60)
        
        # Exibir resultado completo
        full_text = "\n".join(output)
        self.results_text.setPlainText(full_text)
        # Garantir que o scroll vá para o topo
        cursor = self.results_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.results_text.setTextCursor(cursor)
    
    def _on_analysis_error(self, error_msg):
        """Chamado quando há erro na análise."""
        self.compare_btn.setEnabled(True)
        self.compare_btn.setText("Comparar Composições")
        QMessageBox.critical(self, "Erro", f"Erro na análise: {error_msg}")

    def _on_calibrate_clicked(self):
        """Treina o calibrador do draft prior (score → prob real)."""
        self.calibrate_btn.setEnabled(False)
        self.calibrate_btn.setText("Calibrando...")
        self.calibrate_thread = CalibrateDraftPriorThread()
        self.calibrate_thread.finished.connect(self._on_calibrate_finished)
        self.calibrate_thread.error.connect(self._on_calibrate_error)
        self.calibrate_thread.start()

    def _on_calibrate_finished(self, metrics):
        self.calibrate_btn.setEnabled(True)
        self.calibrate_btn.setText("Calibrar draft prior")
        if metrics.get("error"):
            QMessageBox.warning(self, "Calibração", metrics["error"])
            return
        msg = (
            f"Amostras: {metrics.get('n_samples', 0)}\n"
            f"Vitórias time 1: {metrics.get('n_wins', 0)}  Derrotas: {metrics.get('n_losses', 0)}\n"
            f"Acurácia teste: {metrics.get('test_accuracy', 0)*100:.2f}%\n"
            f"Brier score: {metrics.get('brier_score', 0):.4f}\n\n"
            "Calibração ativa: p_draft = σ(a·draft_delta + b). "
            "Próximas comparações exibirão prob. calibrada (60% ≈ 60% real)."
        )
        QMessageBox.information(self, "Calibrador treinado", msg)
        self._update_calibrate_status()

    def _on_calibrate_error(self, err):
        self.calibrate_btn.setEnabled(True)
        self.calibrate_btn.setText("Calibrar draft prior")
        QMessageBox.critical(self, "Erro", err)
