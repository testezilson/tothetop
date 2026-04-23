"""
Página de Pré-bets Secundárias do Dota 2 (kills, torres, barracks, roshans, tempo,
first blood / first 10 / first tower / first roshan via CyberScore).
Layout alinhado à aba LoL: três grupos na mesma linha; odds Time1/Time2 nos mercados CyberScore.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QTextEdit, QGroupBox, QFormLayout,
    QDoubleSpinBox, QSpinBox, QMessageBox, QCheckBox
)
from PySide6.QtCore import QThread, Signal, QLocale
from core.dota.prebets_secondary import DotaSecondaryBetsAnalyzer, CYBERSCORE_OBJECTIVE_COLUMNS


def _dota_stat_display(stat: str) -> str:
    """Nome legível para o cabeçalho (ex.: first_tower -> first tower)."""
    if not stat:
        return ""
    return stat.replace("_", " ").strip()


class FlexibleDoubleSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox que aceita tanto vírgula quanto ponto como separador decimal."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        self.lineEdit().textEdited.connect(self._on_text_edited)
    
    def _on_text_edited(self, text):
        """Intercepta edição de texto e substitui vírgula por ponto."""
        if ',' in text:
            normalized = text.replace(',', '.')
            cursor_pos = self.lineEdit().cursorPosition()
            self.lineEdit().blockSignals(True)
            self.lineEdit().setText(normalized)
            self.lineEdit().setCursorPosition(cursor_pos)
            self.lineEdit().blockSignals(False)
    
    def textFromValue(self, value):
        return super().textFromValue(value)
    
    def valueFromText(self, text):
        if isinstance(text, str):
            text = text.replace(',', '.')
        return super().valueFromText(text)
    
    def validate(self, text, pos):
        if isinstance(text, str):
            normalized_text = text.replace(',', '.')
        else:
            normalized_text = text
        return super().validate(normalized_text, pos)


class DotaSecondaryAnalysisThread(QThread):
    """Thread para executar análise sem travar a UI."""
    finished = Signal(dict)
    error = Signal(str)
    
    def __init__(self, analyzer, team1, team2, stat, line, odd_over, odd_under, limit_games, h2h_months, use_h2h):
        super().__init__()
        self.analyzer = analyzer
        self.team1 = team1
        self.team2 = team2
        self.stat = stat
        self.line = line
        self.odd_over = odd_over
        self.odd_under = odd_under
        self.limit_games = limit_games
        self.h2h_months = h2h_months
        self.use_h2h = use_h2h
    
    def run(self):
        try:
            result = self.analyzer.analyze_bet(
                self.team1,
                self.team2,
                self.stat,
                self.line,
                self.odd_over,
                self.odd_under,
                self.limit_games,
                self.h2h_months,
                self.use_h2h
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class DotaSecondaryBetsPage(QWidget):
    """Página de análise de pré-bets secundárias do Dota 2."""
    
    def __init__(self):
        super().__init__()
        self.analyzer = DotaSecondaryBetsAnalyzer()
        self.analysis_thread = None
        
        self._init_ui()
        self._load_data()
    
    def _init_ui(self):
        """Inicializa a interface (três grupos na mesma linha, como na aba LoL)."""
        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()

        # Grupo de seleção
        selection_group = QGroupBox("Seleção de Jogo")
        selection_layout = QFormLayout()

        self.team1_combo = QComboBox()
        self.team1_combo.setEditable(True)
        selection_layout.addRow("Time 1:", self.team1_combo)

        self.team2_combo = QComboBox()
        self.team2_combo.setEditable(True)
        selection_layout.addRow("Time 2:", self.team2_combo)

        self.stat_combo = QComboBox()
        self.stat_combo.addItems(self.analyzer.get_available_stats())
        self.stat_combo.currentTextChanged.connect(self._on_stat_changed)
        selection_layout.addRow("Estatística:", self.stat_combo)

        selection_group.setLayout(selection_layout)
        top_row.addWidget(selection_group, 1)

        # Grupo de aposta
        bet_group = QGroupBox("Dados da Aposta")
        bet_layout = QFormLayout()

        self.line_spin = FlexibleDoubleSpinBox()
        self.line_spin.setMinimum(0.0)
        self.line_spin.setMaximum(1000.0)
        self.line_spin.setDecimals(1)
        self.line_spin.setValue(45.5)
        bet_layout.addRow("Linha:", self.line_spin)

        self.lbl_odd_a = QLabel("Odd Over:")
        self.odd_over_spin = QDoubleSpinBox()
        self.odd_over_spin.setMinimum(1.01)
        self.odd_over_spin.setMaximum(100.0)
        self.odd_over_spin.setDecimals(2)
        self.odd_over_spin.setValue(1.90)
        bet_layout.addRow(self.lbl_odd_a, self.odd_over_spin)

        self.lbl_odd_b = QLabel("Odd Under:")
        self.odd_under_spin = QDoubleSpinBox()
        self.odd_under_spin.setMinimum(1.01)
        self.odd_under_spin.setMaximum(100.0)
        self.odd_under_spin.setDecimals(2)
        self.odd_under_spin.setValue(1.90)
        bet_layout.addRow(self.lbl_odd_b, self.odd_under_spin)

        self.limit_spin = QSpinBox()
        self.limit_spin.setMinimum(1)
        self.limit_spin.setMaximum(100)
        self.limit_spin.setValue(10)
        bet_layout.addRow("Jogos recentes:", self.limit_spin)

        bet_group.setLayout(bet_layout)
        top_row.addWidget(bet_group, 1)

        # Grupo de H2H
        h2h_group = QGroupBox("Filtros H2H")
        h2h_layout = QFormLayout()

        self.h2h_months_spin = QSpinBox()
        self.h2h_months_spin.setMinimum(1)
        self.h2h_months_spin.setMaximum(24)
        self.h2h_months_spin.setValue(3)
        h2h_layout.addRow("Meses de histórico H2H:", self.h2h_months_spin)

        self.use_h2h_check = QCheckBox()
        self.use_h2h_check.setChecked(False)
        h2h_layout.addRow("Incluir peso H2H:", self.use_h2h_check)

        h2h_group.setLayout(h2h_layout)
        top_row.addWidget(h2h_group, 1)

        layout.addLayout(top_row)
        
        # Botão de calcular
        self.calculate_btn = QPushButton("Calcular")
        self.calculate_btn.clicked.connect(self._calculate)
        layout.addWidget(self.calculate_btn)
        
        # Área de resultados
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.results_text)

        # Rótulos Odd Time 1/2 vs Over/Under conforme estatística inicial
        self._on_stat_changed(self.stat_combo.currentText())
    
    def _on_stat_changed(self, stat: str):
        """Mercados CyberScore: linha 0,5 fixa; odds = Time 1 / Time 2 (como first tower no LoL)."""
        obj = stat in CYBERSCORE_OBJECTIVE_COLUMNS
        self.line_spin.setEnabled(not obj)
        if obj:
            self.line_spin.setValue(0.5)
            self.lbl_odd_a.setText("Odd (Time 1):")
            self.lbl_odd_b.setText("Odd (Time 2):")
            self.odd_over_spin.setToolTip("Odd para o Time 1 conquistar o objetivo")
            self.odd_under_spin.setToolTip("Odd para o Time 2 conquistar o objetivo")
        else:
            self.lbl_odd_a.setText("Odd Over:")
            self.lbl_odd_b.setText("Odd Under:")
            self.odd_over_spin.setToolTip("")
            self.odd_under_spin.setToolTip("")
    
    def _load_data(self):
        """Carrega dados disponíveis."""
        db_path = self.analyzer.get_db_path()
        if db_path is None:
            QMessageBox.warning(
                self, 
                "Erro", 
                "Não foi possível encontrar o banco de dados Dota.\n\n"
                "Verifique se o arquivo está em:\n"
                "- C:\\Users\\Lucas\\Documents\\final\\dota_oracle_v1\\dota_oracle_v1\\cyberscore.db\n"
                "- C:\\Users\\Lucas\\Documents\\final\\dota_oracle_v1\\dota_oracle_v1\\data\\dota_matches_stratz.db"
            )
            return
        
        # Carregar times
        try:
            teams = self.analyzer.get_available_teams()
            if teams:
                self.team1_combo.addItems([""] + teams)
                self.team2_combo.addItems([""] + teams)
            else:
                QMessageBox.warning(
                    self,
                    "Aviso",
                    "Banco de dados encontrado, mas nenhum time foi encontrado.\n"
                    "Verifique se o banco contém dados."
                )
        except Exception as e:
            QMessageBox.warning(
                self,
                "Erro",
                f"Erro ao carregar times do banco:\n{str(e)}"
            )
    
    def _calculate(self):
        """Calcula análise da aposta."""
        team1 = self.team1_combo.currentText().strip()
        team2 = self.team2_combo.currentText().strip()
        stat = self.stat_combo.currentText()
        line = self.line_spin.value()
        odd_over = self.odd_over_spin.value()
        odd_under = self.odd_under_spin.value()
        limit_games = self.limit_spin.value()
        
        if not team1 or not team2:
            QMessageBox.warning(self, "Erro", "Selecione ambos os times.")
            return
        
        if team1 == team2:
            QMessageBox.warning(self, "Erro", "Os times devem ser diferentes.")
            return
        
        # Desabilitar botão durante cálculo
        self.calculate_btn.setEnabled(False)
        self.calculate_btn.setText("Calculando...")
        
        # Parâmetros H2H
        h2h_months = self.h2h_months_spin.value()
        use_h2h = self.use_h2h_check.isChecked()

        self._pending_analysis = (team1, team2, stat)

        # Executar em thread separada
        self.analysis_thread = DotaSecondaryAnalysisThread(
            self.analyzer, team1, team2, stat, line, odd_over, odd_under, limit_games, h2h_months, use_h2h
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
        
        if "error" in result:
            QMessageBox.warning(self, "Erro", result["error"])
            return

        pending = getattr(self, "_pending_analysis", None)
        if pending is not None:
            req_team1, req_team2, req_stat = pending
            if (result.get("team1"), result.get("team2"), result.get("stat")) != (req_team1, req_team2, req_stat):
                return

        output = []
        is_first = result.get("is_first_stat", False)
        stat_display = _dota_stat_display(result.get("stat", ""))

        output.append("=" * 80)
        output.append(f"📊 {stat_display.upper()} — {result['team1']} vs {result['team2']}")
        output.append("=" * 80)
        output.append("")

        if is_first:
            output.append("📉 Taxa de conquista por time (qual time pegou o objetivo):")
            output.append("")
        else:
            output.append("📉 Estatísticas por time:")
        output.append("")
        output.append(f"🔵 {result['team1']}")
        if is_first:
            output.append(
                f"• Taxa: {result['mean_team1']*100:.1f}% ({result['team1_over']}/{result['team1_games']} pegou)."
            )
            im1 = int(result.get("team1_objective_imputed_games") or 0)
            k1 = int(result.get("team1_objective_known_games") or 0)
            mc1 = int(result.get("team1_objective_missing_column") or 0)
            mu1 = int(result.get("team1_objective_unmapped_team") or 0)
            if k1 > 0 and (im1 > 0 or k1 != result["team1_games"]):
                pct_k = 100.0 * result["team1_over"] / k1
                output.append(
                    f"   ↳ Taxa só com dado no banco: {pct_k:.1f}% ({result['team1_over']}/{k1} pegou)."
                )
            if im1 > 0:
                bits = []
                if mc1:
                    bits.append(
                        f"{mc1} sem valor na coluna «{stat_display}» no SQLite (site pode ter dado; falta scrape/import/repair)"
                    )
                if mu1:
                    bits.append(
                        f"{mu1} com flag no banco mas nome do time não casou Radiant/Dire nesta linha (ver nomes no banco vs combo)"
                    )
                tail = " ".join(bits) if bits else "motivo não detalhado"
                output.append(
                    f"   ↳ Dos últimos {result['team1_games']} jogos, {im1} entraram como buraco local: {tail}."
                )
        else:
            output.append(f"• Média: {result['mean_team1']:.2f} ({result['team1_games']} jogos)")
            if result["team1_games"] > 0:
                output.append(
                    f"• UNDER: {result['team1_under']} jogos ({result['team1_under']/result['team1_games']*100:.2f}%)"
                )
                output.append(
                    f"• OVER:  {result['team1_over']} jogos ({result['team1_over']/result['team1_games']*100:.2f}%)"
                )
        output.append("")
        output.append(f"🔴 {result['team2']}")
        if is_first:
            output.append(
                f"• Taxa: {result['mean_team2']*100:.1f}% ({result['team2_over']}/{result['team2_games']} pegou)."
            )
            im2 = int(result.get("team2_objective_imputed_games") or 0)
            k2 = int(result.get("team2_objective_known_games") or 0)
            mc2 = int(result.get("team2_objective_missing_column") or 0)
            mu2 = int(result.get("team2_objective_unmapped_team") or 0)
            if k2 > 0 and (im2 > 0 or k2 != result["team2_games"]):
                pct_k2 = 100.0 * result["team2_over"] / k2
                output.append(
                    f"   ↳ Taxa só com dado no banco: {pct_k2:.1f}% ({result['team2_over']}/{k2} pegou)."
                )
            if im2 > 0:
                bits2 = []
                if mc2:
                    bits2.append(
                        f"{mc2} sem valor na coluna «{stat_display}» no SQLite (site pode ter dado; falta scrape/import/repair)"
                    )
                if mu2:
                    bits2.append(
                        f"{mu2} com flag no banco mas nome do time não casou Radiant/Dire nesta linha (ver nomes no banco vs combo)"
                    )
                tail2 = " ".join(bits2) if bits2 else "motivo não detalhado"
                output.append(
                    f"   ↳ Dos últimos {result['team2_games']} jogos, {im2} entraram como buraco local: {tail2}."
                )
        else:
            output.append(f"• Média: {result['mean_team2']:.2f} ({result['team2_games']} jogos)")
            if result["team2_games"] > 0:
                output.append(
                    f"• UNDER: {result['team2_under']} jogos ({result['team2_under']/result['team2_games']*100:.2f}%)"
                )
                output.append(
                    f"• OVER:  {result['team2_over']} jogos ({result['team2_over']/result['team2_games']*100:.2f}%)"
                )
        output.append("")

        total_games = result["team1_games"] + result["team2_games"]
        if is_first:
            output.append(f"📊 Probabilidades para o confronto ({stat_display}):")
            output.append(f"• Time 1: {result['prob_over']*100:.2f}%")
            output.append(f"• Time 2: {result['prob_under']*100:.2f}%")
        else:
            output.append(f"📊 Estatísticas combinadas ({total_games} jogos, {result['stat']}):")
            if total_games > 0:
                output.append(f"• UNDER: {result['under_all']} ({result['under_all']/total_games*100:.2f}%)")
                output.append(f"• OVER:  {result['over_all']} ({result['over_all']/total_games*100:.2f}%)")
        output.append("")

        if result.get("use_h2h"):
            output.append("=" * 80)
            output.append("HISTORICO H2H")
            output.append("=" * 80)
            output.append("")
            if result.get("h2h_games", 0) == 0:
                output.append("Nenhum jogo H2H encontrado no periodo.")
            elif result.get("h2h_rate") is not None:
                output.append(f"Jogos H2H encontrados: {result['h2h_games']}")
                if is_first:
                    output.append(f"Time 1 pegou: {result['h2h_over']} jogos ({result['h2h_rate']*100:.2f}%)")
                    output.append(f"Time 2 pegou: {result['h2h_under']} jogos ({(1-result['h2h_rate'])*100:.2f}%)")
                else:
                    output.append(f"Media H2H: {result['h2h_mean']:.2f}")
                    output.append(f"OVER {result['line']}: {result['h2h_over']} jogos ({result['h2h_rate']*100:.2f}%)")
                    output.append(
                        f"UNDER {result['line']}: {result['h2h_under']} jogos ({(1-result['h2h_rate'])*100:.2f}%)"
                    )
                output.append("")
                output.append(f"Peso H2H: {result['w_h2h']*100:.1f}% | Peso Forma: {result['w_form']*100:.1f}%")
            output.append("")

        output.append("=" * 80)
        output.append("📈 PROBABILIDADES")
        output.append("=" * 80)
        output.append("")
        if result.get("use_h2h") and result.get("h2h_rate") is not None:
            output.append(f"Prob. Empírica (Forma): {result['prob_form']*100:.2f}%")
            output.append(f"Prob. H2H: {result['h2h_rate']*100:.2f}%")
            output.append("")
        if is_first:
            output.append(f"Prob. Time 1: {result['prob_over']*100:.2f}%")
            output.append(f"Prob. Time 2: {result['prob_under']*100:.2f}%")
        else:
            output.append(f"Prob. Over {result['line']}:  {result['prob_over']*100:.2f}%")
            output.append(f"Prob. Under {result['line']}: {result['prob_under']*100:.2f}%")
        output.append("")

        output.append("=" * 80)
        output.append("💰 EV E FAIR ODDS (Formato Pinnacle)")
        output.append("=" * 80)
        output.append("")
        if is_first:
            output.append(
                f"Time 1: EV = {result['ev_over']:+.2f}u ({result['ev_over_pct']:+.2%}) | Fair = {result['fair_over']:.3f}"
            )
            output.append(
                f"Time 2: EV = {result['ev_under']:+.2f}u ({result['ev_under_pct']:+.2%}) | Fair = {result['fair_under']:.3f}"
            )
        else:
            output.append(
                f"Over  {result['line']}: EV = {result['ev_over']:+.2f}u ({result['ev_over_pct']:+.2%}) | Fair = {result['fair_over']:.3f}"
            )
            output.append(
                f"Under {result['line']}: EV = {result['ev_under']:+.2f}u ({result['ev_under_pct']:+.2%}) | Fair = {result['fair_under']:.3f}"
            )
        output.append("")

        if "Nenhuma" in result["recommendation"]:
            output.append(f"❌ {result['recommendation']}")
        else:
            output.append(f"✅ {result['recommendation']}")
        
        # Exibir resultado
        self.results_text.setPlainText("\n".join(output))
        self.results_text.verticalScrollBar().setValue(0)
    
    def _on_analysis_error(self, error_msg):
        """Chamado quando há erro na análise."""
        self.calculate_btn.setEnabled(True)
        self.calculate_btn.setText("Calcular")
        QMessageBox.critical(self, "Erro", f"Erro ao calcular: {error_msg}")
