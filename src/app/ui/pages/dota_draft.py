"""
Página de Draft Live do Dota 2.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QGroupBox, QFormLayout,
    QMessageBox, QTextEdit, QSpinBox
)
from PySide6.QtCore import Qt, QThread, Signal
from core.dota.draft import DotaDraftAnalyzer


class DotaDraftAnalysisThread(QThread):
    """Thread para executar análise de draft sem travar a UI."""
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


class DotaDraftPage(QWidget):
    """Página de análise de draft do Dota 2."""
    
    def __init__(self):
        super().__init__()
        self.analyzer = DotaDraftAnalyzer()
        self.analysis_thread = None
        
        self._init_ui()
        self._load_data()
    
    def _init_ui(self):
        """Inicializa a interface."""
        layout = QVBoxLayout(self)
        
        # Grupo de configuração
        config_group = QGroupBox("Configuração")
        config_layout = QFormLayout()
        
        # Nome do Time Radiant
        self.radiant_team_input = QLineEdit()
        self.radiant_team_input.setPlaceholderText("Ex: Team Liquid, OG, Spirit")
        config_layout.addRow("Nome Time Radiant:", self.radiant_team_input)
        
        # Nome do Time Dire
        self.dire_team_input = QLineEdit()
        self.dire_team_input.setPlaceholderText("Ex: PSG.LGD, BetBoom, GG")
        config_layout.addRow("Nome Time Dire:", self.dire_team_input)
        
        # Número de jogos para média dos times
        self.n_games_spin = QSpinBox()
        self.n_games_spin.setMinimum(15)
        self.n_games_spin.setMaximum(100)
        self.n_games_spin.setValue(15)
        config_layout.addRow("Jogos para média dos times:", self.n_games_spin)
        
        config_group.setLayout(config_layout)
        layout.addWidget(config_group)
        
        # Times
        teams_layout = QHBoxLayout()
        
        # Radiant
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
        
        # Dire
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
        self.details_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        results_layout.addWidget(self.details_text)
        
        layout.addLayout(results_layout)
    
    def _load_data(self):
        """Carrega dados disponíveis."""
        try:
            if not self.analyzer.load_models():
                import os
                dota_dir = r"C:\Users\Lucas\Documents\final\dota_oracle_v1\dota_oracle_v1\dota_draft_ml_v1"
                dir_exists = os.path.exists(dota_dir)
                
                # Verificar quais arquivos estão faltando
                required_files = [
                    "trained_models_dota_v2.pkl",
                    "hero_impacts_bayesian_single.pkl",
                    "scaler_dota_v2.pkl"
                ]
                missing = []
                if dir_exists:
                    for file in required_files:
                        file_path = os.path.join(dota_dir, file)
                        if not os.path.exists(file_path):
                            missing.append(file)
                
                error_msg = "Não foi possível carregar os modelos Dota.\n\n"
                if not dir_exists:
                    error_msg += f"[X] Diretorio nao encontrado:\n{dota_dir}\n\n"
                else:
                    error_msg += f"[OK] Diretorio encontrado: {dota_dir}\n\n"
                    if missing:
                        error_msg += f"[X] Arquivos faltando:\n" + "\n".join(f"  - {f}" for f in missing) + "\n\n"
                    else:
                        error_msg += "[AVISO] Todos os arquivos existem, mas houve erro ao carregar.\n\n"
                        
                        # Adicionar erro específico se disponível
                        if hasattr(self.analyzer, 'last_error') and self.analyzer.last_error:
                            error_msg += "Erro detalhado:\n"
                            error_msg += "─" * 50 + "\n"
                            # Pegar apenas as primeiras linhas do erro para não sobrecarregar
                            error_lines = self.analyzer.last_error.split('\n')[:10]
                            error_msg += "\n".join(error_lines)
                            if len(self.analyzer.last_error.split('\n')) > 10:
                                error_msg += "\n... (erro truncado)"
                            error_msg += "\n" + "─" * 50 + "\n\n"
                        
                        error_msg += "Possíveis causas:\n"
                        error_msg += "• Arquivos .pkl corrompidos\n"
                        error_msg += "• Versão incompatível do Python/pickle\n"
                        error_msg += "• Dependências faltando (scipy, sklearn, etc.)\n"
                        error_msg += "• Modelos criados com versão diferente do Python"
                
                QMessageBox.warning(self, "Erro", error_msg)
                return
            
            # Carregar heróis
            heroes = self.analyzer.get_available_heroes()
            if heroes:
                for pick_combo in self.radiant_picks + self.dire_picks:
                    pick_combo.addItems([""] + heroes)
            else:
                QMessageBox.warning(
                    self,
                    "Aviso",
                    "Nenhum herói encontrado nos dados."
                )
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao carregar dados: {str(e)}")
    
    def _calculate(self):
        """Calcula análise do draft."""
        # Coletar picks
        radiant_picks = []
        dire_picks = []
        
        for pick_combo in self.radiant_picks:
            hero = pick_combo.currentText().strip()
            if hero:
                radiant_picks.append(hero)
        
        for pick_combo in self.dire_picks:
            hero = pick_combo.currentText().strip()
            if hero:
                dire_picks.append(hero)
        
        if len(radiant_picks) == 0 and len(dire_picks) == 0:
            QMessageBox.warning(self, "Erro", "Adicione pelo menos um herói.")
            return
        
        # Coletar nomes dos times (opcional)
        radiant_team_name = self.radiant_team_input.text().strip() or None
        dire_team_name = self.dire_team_input.text().strip() or None
        n_games = self.n_games_spin.value()
        
        # Desabilitar botão durante cálculo
        self.calculate_btn.setEnabled(False)
        self.calculate_btn.setText("Analisando...")
        
        # Executar em thread separada
        self.analysis_thread = DotaDraftAnalysisThread(
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
        
        if "error" in result:
            QMessageBox.warning(self, "Erro", result["error"])
            return
        
        # Atualizar tabela de linhas
        self.lines_table.setRowCount(0)
        predictions = result.get("predictions", {})
        
        for line, pred in sorted(predictions.items()):
            row = self.lines_table.rowCount()
            self.lines_table.insertRow(row)
            
            self.lines_table.setItem(row, 0, QTableWidgetItem(f"{line:.1f}"))
            self.lines_table.setItem(row, 1, QTableWidgetItem(f"{pred['prob_under']*100:.1f}%"))
            self.lines_table.setItem(row, 2, QTableWidgetItem(f"{pred['prob_over']*100:.1f}%"))
            
            # Recomendação com cor
            rec_item = QTableWidgetItem(f"{pred['favorite']} ({pred['confidence']})")
            if pred['confidence'] in ["Very High", "High"]:
                rec_item.setForeground(Qt.GlobalColor.green)
            elif pred['confidence'] == "Medium":
                rec_item.setForeground(Qt.GlobalColor.yellow)
            else:
                rec_item.setForeground(Qt.GlobalColor.red)
            self.lines_table.setItem(row, 3, rec_item)
        
        self.lines_table.resizeColumnsToContents()
        
        # Atualizar detalhes
        details = []
        details.append("=" * 80)
        details.append("📊 ANÁLISE DE DRAFT - DOTA 2 (COM FATOR TIMES)")
        details.append("=" * 80)
        details.append("")
        
        # Informações dos times
        radiant_team = result.get("team_factor", {}).get("radiant_team_name", "Radiant")
        dire_team = result.get("team_factor", {}).get("dire_team_name", "Dire")
        details.append(f"🟩 {radiant_team} vs 🟥 {dire_team}")
        details.append("")
        
        # Fator times empírico
        team_factor = result.get("team_factor")
        if team_factor and team_factor.get("method") == "empirical_by_line":
            details.append("=" * 80)
            details.append("📈 FATOR TIMES (EMPÍRICO POR LINHA)")
            details.append("=" * 80)
            details.append(f"Método: Probabilidades empíricas de OVER/UNDER por linha")
            details.append(f"Peso Draft: {team_factor.get('weight_draft', 0.65):.0%} | Peso Times: {team_factor.get('weight_times', 0.35):.0%}")
            details.append("")
            details.append(f"Time Radiant ({radiant_team}): {team_factor['radiant_n_games']} jogos")
            details.append(f"Time Dire ({dire_team}): {team_factor['dire_n_games']} jogos")
            details.append("")
            details.append("Probabilidades empíricas por linha (exemplos):")
            
            # Mostrar algumas linhas como exemplo
            sample_lines = [45.5, 47.5, 50.5, 52.5]
            for line in sample_lines:
                if line in team_factor.get('radiant_probs', {}) and line in team_factor.get('dire_probs', {}):
                    p_rad = team_factor['radiant_probs'][line]
                    p_dir = team_factor['dire_probs'][line]
                    p_combined = (p_rad + p_dir) / 2
                    details.append(f"  Linha {line:>4.1f}: Radiant={p_rad:.1%} | Dire={p_dir:.1%} | Média={p_combined:.1%}")
            
            details.append("")
            details.append("ℹ️ Combinação via log-odds: logit(p_final) = w_draft*logit(p_draft) + w_times*logit(p_times)")
        elif team_factor:
            # Formato antigo (compatibilidade)
            details.append("=" * 80)
            details.append("📈 FATOR TIMES")
            details.append("=" * 80)
            details.append("⚠️ Formato antigo detectado. Use nomes dos times para método empírico.")
        else:
            details.append("⚠️ Fator times não calculado (nomes dos times não fornecidos)")
        
        details.append("")
        
        # Impactos individuais
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
        details.append(f"")
        details.append(f"🎯 Kills estimadas: {result['kills_estimadas']:.2f} (apenas para referência)")
        details.append("")
        
        # Previsões detalhadas
        details.append("=" * 80)
        details.append("📊 PREVISÕES POR LINHA (DRAFT + TIMES)")
        details.append("=" * 80)
        for line, pred in sorted(predictions.items()):
            favorite = pred['favorite']
            prob_final = pred['prob_over'] * 100 if favorite == 'OVER' else pred['prob_under'] * 100
            
            # Mostrar breakdown se tiver fator times
            if pred.get('prob_times_over') is not None:
                prob_draft = pred['prob_draft_over'] * 100
                prob_times = pred['prob_times_over'] * 100
                details.append(f"Linha {line:>4.1f}: {favorite:>4} | Final: {prob_final:>5.1f}% | Draft: {prob_draft:>5.1f}% | Times: {prob_times:>5.1f}% | {pred['confidence']}")
            else:
                details.append(f"Linha {line:>4.1f}: {favorite:>4} | Prob({favorite}): {prob_final:>6.1f}% | Confiança: {pred['confidence']}")
        
        self.details_text.setPlainText("\n".join(details))
        self.details_text.verticalScrollBar().setValue(0)
    
    def _on_analysis_error(self, error_msg):
        """Chamado quando há erro na análise."""
        self.calculate_btn.setEnabled(True)
        self.calculate_btn.setText("Analisar Draft")
        QMessageBox.critical(self, "Erro", f"Erro ao calcular: {error_msg}")
