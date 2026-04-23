"""
Página TESTE: mesmo layout do Dota - Draft Live, com cálculos do projeto testezudo (v2.7).
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QGroupBox, QFormLayout,
    QMessageBox, QTextEdit, QSpinBox
)
from PySide6.QtCore import Qt, QThread, Signal
from core.dota.draft_testezudo import DotaDraftTestezudoAnalyzer


class DotaDraftTesteAnalysisThread(QThread):
    """Thread para executar análise de draft (testezudo) sem travar a UI."""
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, analyzer, radiant_picks, dire_picks, radiant_team_name=None, dire_team_name=None, n_games=15):
        super().__init__()
        self.analyzer = analyzer
        self.radiant_picks = radiant_picks
        self.dire_picks = dire_picks
        self.radiant_team_name = radiant_team_name
        self.dire_team_name = dire_team_name
        self.n_games = n_games

    def run(self):
        try:
            result = self.analyzer.analyze_draft(
                self.radiant_picks,
                self.dire_picks,
                self.radiant_team_name,
                self.dire_team_name,
                self.n_games
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class DotaDraftTestePage(QWidget):
    """Página de análise de draft Dota 2 - TESTE (matemática testezudo v2.7). Mesmo layout que Dota - Draft Live."""

    def __init__(self):
        super().__init__()
        self.analyzer = DotaDraftTestezudoAnalyzer()
        self.analysis_thread = None

        self._init_ui()
        self._load_data()

    def _init_ui(self):
        """Inicializa a interface (igual ao Dota - Draft Live)."""
        layout = QVBoxLayout(self)

        # Grupo de configuração
        config_group = QGroupBox("Configuração")
        config_layout = QFormLayout()

        self.radiant_team_input = QLineEdit()
        self.radiant_team_input.setPlaceholderText("Ex: Team Liquid, OG, Spirit")
        config_layout.addRow("Nome Time Radiant:", self.radiant_team_input)

        self.dire_team_input = QLineEdit()
        self.dire_team_input.setPlaceholderText("Ex: PSG.LGD, BetBoom, GG")
        config_layout.addRow("Nome Time Dire:", self.dire_team_input)

        self.n_games_spin = QSpinBox()
        self.n_games_spin.setMinimum(15)
        self.n_games_spin.setMaximum(100)
        self.n_games_spin.setValue(15)
        config_layout.addRow("Jogos para média dos times:", self.n_games_spin)

        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        # Times
        teams_layout = QHBoxLayout()

        radiant_group = QGroupBox("Radiant")
        radiant_layout = QFormLayout()
        self.radiant_picks = []
        for i in range(5):
            pick = QComboBox()
            pick.setEditable(True)
            pick.setPlaceholderText(f"Herói {i+1}")
            self.radiant_picks.append(pick)
            radiant_layout.addRow(f"Pick {i+1}:", pick)
        radiant_group.setLayout(radiant_layout)
        teams_layout.addWidget(radiant_group)

        dire_group = QGroupBox("Dire")
        dire_layout = QFormLayout()
        self.dire_picks = []
        for i in range(5):
            pick = QComboBox()
            pick.setEditable(True)
            pick.setPlaceholderText(f"Herói {i+1}")
            self.dire_picks.append(pick)
            dire_layout.addRow(f"Pick {i+1}:", pick)
        dire_group.setLayout(dire_layout)
        teams_layout.addWidget(dire_group)

        layout.addLayout(teams_layout)

        self.calculate_btn = QPushButton("Analisar Draft")
        self.calculate_btn.clicked.connect(self._calculate)
        layout.addWidget(self.calculate_btn)

        # Resultados
        results_layout = QHBoxLayout()
        self.lines_table = QTableWidget()
        self.lines_table.setColumnCount(4)
        self.lines_table.setHorizontalHeaderLabels([
            "Linha", "Prob(UNDER)", "Prob(OVER)", "Recomendação"
        ])
        results_layout.addWidget(self.lines_table)

        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        results_layout.addWidget(self.details_text)

        layout.addLayout(results_layout)

    def _load_data(self):
        """Carrega dados do projeto testezudo."""
        try:
            if not self.analyzer.load_models():
                import os
                dota_dir = self.analyzer.testezudo_dir
                dir_exists = os.path.exists(dota_dir)
                required_files = [
                    "models_dota_v2_7.pkl",
                    "hero_impacts_bayesian_single.pkl",
                    "config_dota_v2_7.pkl",
                ]
                missing = []
                if dir_exists:
                    for f in required_files:
                        if not os.path.exists(os.path.join(dota_dir, f)):
                            missing.append(f)
                error_msg = "Não foi possível carregar os modelos TESTE (testezudo v2.7).\n\n"
                if not dir_exists:
                    error_msg += f"[X] Diretório não encontrado:\n{dota_dir}\n\n"
                else:
                    error_msg += f"[OK] Diretório: {dota_dir}\n\n"
                    if missing:
                        error_msg += f"[X] Arquivos faltando:\n" + "\n".join(f"  - {f}" for f in missing) + "\n\n"
                    elif hasattr(self.analyzer, "last_error") and self.analyzer.last_error:
                        error_msg += "Erro ao carregar:\n" + self.analyzer.last_error[:500] + "\n\n"
                QMessageBox.warning(self, "Erro", error_msg)
                return

            heroes = self.analyzer.get_available_heroes()
            if heroes:
                for pick_combo in self.radiant_picks + self.dire_picks:
                    pick_combo.addItems([""] + heroes)
            else:
                QMessageBox.warning(self, "Aviso", "Nenhum herói encontrado nos dados testezudo.")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao carregar dados: {str(e)}")

    def _calculate(self):
        """Calcula análise do draft (testezudo v2.7)."""
        radiant_picks = [p.currentText().strip() for p in self.radiant_picks if p.currentText().strip()]
        dire_picks = [p.currentText().strip() for p in self.dire_picks if p.currentText().strip()]

        if len(radiant_picks) == 0 and len(dire_picks) == 0:
            QMessageBox.warning(self, "Erro", "Adicione pelo menos um herói.")
            return

        # Recarregar .pkl do disco para pegar dados atualizados (ex.: após "Atualizar Banco Dota Draft Live")
        self.analyzer.reload_models()

        radiant_team_name = self.radiant_team_input.text().strip() or None
        dire_team_name = self.dire_team_input.text().strip() or None
        n_games = self.n_games_spin.value()

        self.calculate_btn.setEnabled(False)
        self.calculate_btn.setText("Analisando...")

        self.analysis_thread = DotaDraftTesteAnalysisThread(
            self.analyzer, radiant_picks, dire_picks, radiant_team_name, dire_team_name, n_games
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
        if result.get("error"):
            QMessageBox.warning(self, "Erro", result["error"])
            return

        predictions = result.get("predictions", {})
        self.lines_table.setRowCount(0)
        for line, pred in sorted(predictions.items()):
            row = self.lines_table.rowCount()
            self.lines_table.insertRow(row)
            self.lines_table.setItem(row, 0, QTableWidgetItem(f"{line:.1f}"))
            self.lines_table.setItem(row, 1, QTableWidgetItem(f"{pred['prob_under']*100:.1f}%"))
            self.lines_table.setItem(row, 2, QTableWidgetItem(f"{pred['prob_over']*100:.1f}%"))
            rec_item = QTableWidgetItem(f"{pred['favorite']} ({pred['confidence']})")
            if pred["confidence"] in ["Very High", "High"]:
                rec_item.setForeground(Qt.GlobalColor.green)
            elif pred["confidence"] == "Medium":
                rec_item.setForeground(Qt.GlobalColor.yellow)
            else:
                rec_item.setForeground(Qt.GlobalColor.red)
            self.lines_table.setItem(row, 3, rec_item)
        self.lines_table.resizeColumnsToContents()

        # Detalhes (igual Draft Live; sem fator times)
        details = []
        details.append("=" * 80)
        details.append("📊 ANÁLISE DE DRAFT - TESTE (testezudo v2.7)")
        details.append("Curva isotônica + Draft Strength (S) + min_games. Sem fator times.")
        details.append("=" * 80)
        details.append("")

        radiant_team = result.get("team_factor", {}).get("radiant_team_name", "Radiant") if result.get("team_factor") else "Radiant"
        dire_team = result.get("team_factor", {}).get("dire_team_name", "Dire") if result.get("team_factor") else "Dire"
        details.append(f"🟩 {radiant_team} vs 🟥 {dire_team}")
        details.append("")
        details.append("ℹ️ Esta aba usa apenas o draft (impactos bayesianos + média global).")
        details.append("   Nomes dos times e jogos são ignorados (sem fator times empírico).")
        details.append("")

        details.append("🟩 RADIANT:")
        for impact_data in result.get("radiant_impacts", []):
            hero = impact_data["hero"]
            impact = impact_data["impact"]
            games = impact_data["games"]
            sinal = "🟢" if impact >= 0 else "🔴"
            details.append(f"  {hero:<20} → {impact:+.2f} {sinal} | {games:>4} jogos")
        details.append("")
        details.append("🟥 DIRE:")
        for impact_data in result.get("dire_impacts", []):
            hero = impact_data["hero"]
            impact = impact_data["impact"]
            games = impact_data["games"]
            sinal = "🟢" if impact >= 0 else "🔴"
            details.append(f"  {hero:<20} → {impact:+.2f} {sinal} | {games:>4} jogos")
        details.append("")
        details.append("=" * 80)
        details.append("📈 IMPACTO TOTAL DO DRAFT")
        details.append("=" * 80)
        details.append(f"Radiant total: {result['radiant_total']:+.2f}")
        details.append(f"Dire total:    {result['dire_total']:+.2f}")
        details.append(f"Total geral:   {result['total_geral']:+.2f}")
        details.append("")
        details.append(f"🎯 Kills estimadas (global_mean + draft_total): {result['kills_estimadas']:.2f}")
        details.append("")
        details.append("=" * 80)
        details.append("📊 PREVISÕES POR LINHA (curva v2.7)")
        details.append("=" * 80)
        for line, pred in sorted(predictions.items()):
            favorite = pred["favorite"]
            prob_final = pred["prob_over"] * 100 if favorite == "OVER" else pred["prob_under"] * 100
            details.append(f"Linha {line:>4.1f}: {favorite:>4} | Prob({favorite}): {prob_final:>6.1f}% | Confiança: {pred['confidence']}")

        self.details_text.setPlainText("\n".join(details))
        self.details_text.verticalScrollBar().setValue(0)

    def _on_analysis_error(self, error_msg):
        """Chamado quando há erro na análise."""
        self.calculate_btn.setEnabled(True)
        self.calculate_btn.setText("Analisar Draft")
        QMessageBox.critical(self, "Erro", f"Erro ao calcular: {error_msg}")
