"""
Página de Pré-bets de Players do LoL (kills, deaths, assists).
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QLineEdit, QTextEdit, QGroupBox, QFormLayout,
    QDoubleSpinBox, QSpinBox, QMessageBox
)
from PySide6.QtCore import Qt, QThread, Signal, QLocale
from core.lol.prebets_player import LoLPlayerBetsAnalyzer


class FlexibleDoubleSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox que aceita tanto vírgula quanto ponto como separador decimal."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Configurar para aceitar ponto como separador (padrão interno)
        self.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        # Conectar ao sinal de edição para interceptar entrada
        self.lineEdit().textEdited.connect(self._on_text_edited)
    
    def _on_text_edited(self, text):
        """Intercepta edição de texto e substitui vírgula por ponto."""
        if ',' in text:
            # Substituir vírgula por ponto
            normalized = text.replace(',', '.')
            # Obter posição do cursor antes de alterar
            cursor_pos = self.lineEdit().cursorPosition()
            # Atualizar o texto do lineEdit
            self.lineEdit().blockSignals(True)  # Evitar loop infinito
            self.lineEdit().setText(normalized)
            # Ajustar posição do cursor (mantém a mesma posição, já que vírgula e ponto têm mesmo tamanho)
            new_cursor_pos = cursor_pos
            self.lineEdit().setCursorPosition(new_cursor_pos)
            self.lineEdit().blockSignals(False)
    
    def textFromValue(self, value):
        """Converte valor para texto usando ponto."""
        return super().textFromValue(value)
    
    def valueFromText(self, text):
        """Converte texto para valor, aceitando tanto vírgula quanto ponto."""
        # Substituir vírgula por ponto antes de converter
        if isinstance(text, str):
            text = text.replace(',', '.')
        return super().valueFromText(text)
    
    def validate(self, text, pos):
        """Valida entrada, aceitando vírgula ou ponto."""
        # Substituir vírgula por ponto temporariamente para validação
        if isinstance(text, str):
            normalized_text = text.replace(',', '.')
        else:
            normalized_text = text
        result = super().validate(normalized_text, pos)
        return result


class PlayerAnalysisThread(QThread):
    """Thread para executar análise sem travar a UI."""
    finished = Signal(dict)
    error = Signal(str)
    
    def __init__(self, analyzer, player_name, stat, line, odd_over, odd_under, n_recent):
        super().__init__()
        self.analyzer = analyzer
        self.player_name = player_name
        self.stat = stat
        self.line = line
        self.odd_over = odd_over
        self.odd_under = odd_under
        self.n_recent = n_recent
    
    def run(self):
        try:
            result = self.analyzer.analyze_bet(
                self.player_name,
                self.stat,
                self.line,
                self.odd_over,
                self.odd_under,
                self.n_recent
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class LoLPlayerBetsPage(QWidget):
    """Página de análise de pré-bets de players do LoL."""
    
    def __init__(self):
        super().__init__()
        self.analyzer = LoLPlayerBetsAnalyzer()
        self.analysis_thread = None
        
        self._init_ui()
        self._load_data()
    
    def _init_ui(self):
        """Inicializa a interface."""
        layout = QVBoxLayout(self)
        
        # Grupo de seleção
        selection_group = QGroupBox("Seleção de Player")
        selection_layout = QFormLayout()
        
        # Player
        player_layout = QHBoxLayout()
        self.player_combo = QComboBox()
        self.player_combo.setEditable(True)
        self.player_combo.setMinimumWidth(200)
        player_layout.addWidget(self.player_combo)
        
        self.search_btn = QPushButton("Buscar")
        self.search_btn.clicked.connect(self._search_players)
        player_layout.addWidget(self.search_btn)
        
        selection_layout.addRow("Player:", player_layout)
        
        # Estatística
        self.stat_combo = QComboBox()
        self.stat_combo.addItems(["kills", "deaths", "assists"])
        selection_layout.addRow("Estatística:", self.stat_combo)
        
        selection_group.setLayout(selection_layout)
        layout.addWidget(selection_group)
        
        # Grupo de aposta
        bet_group = QGroupBox("Dados da Aposta")
        bet_layout = QFormLayout()
        
        # Linha - usar campo customizado que aceita vírgula e ponto
        self.line_spin = FlexibleDoubleSpinBox()
        self.line_spin.setMinimum(0.0)
        self.line_spin.setMaximum(100.0)
        self.line_spin.setDecimals(1)
        self.line_spin.setValue(5.5)
        bet_layout.addRow("Linha:", self.line_spin)
        
        # Odd Over
        self.odd_over_spin = QDoubleSpinBox()
        self.odd_over_spin.setMinimum(1.01)
        self.odd_over_spin.setMaximum(100.0)
        self.odd_over_spin.setDecimals(2)
        self.odd_over_spin.setValue(1.90)
        bet_layout.addRow("Odd Over:", self.odd_over_spin)
        
        # Odd Under
        self.odd_under_spin = QDoubleSpinBox()
        self.odd_under_spin.setMinimum(1.01)
        self.odd_under_spin.setMaximum(100.0)
        self.odd_under_spin.setDecimals(2)
        self.odd_under_spin.setValue(1.90)
        bet_layout.addRow("Odd Under:", self.odd_under_spin)
        
        # Jogos recentes
        self.n_recent_spin = QSpinBox()
        self.n_recent_spin.setMinimum(1)
        self.n_recent_spin.setMaximum(100)
        self.n_recent_spin.setValue(10)
        bet_layout.addRow("Jogos recentes:", self.n_recent_spin)
        
        bet_group.setLayout(bet_layout)
        layout.addWidget(bet_group)
        
        # Botão de calcular
        self.calculate_btn = QPushButton("Calcular")
        self.calculate_btn.clicked.connect(self._calculate)
        layout.addWidget(self.calculate_btn)
        
        # Área de resultados
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.results_text)
    
    def _load_data(self):
        """Carrega dados disponíveis."""
        # Verificar se o banco existe ou pode ser criado
        db_path = self.analyzer.get_db_path()
        if db_path is None:
            # Tentar criar o banco
            try:
                from core.lol.db_converter import ensure_db_exists
                db_path = ensure_db_exists()
                if db_path:
                    self.analyzer.db_path = db_path
                else:
                    QMessageBox.warning(
                        self, 
                        "Erro", 
                        "Não foi possível encontrar ou criar o banco de dados.\n\n"
                        "Verifique se o arquivo CSV está em:\n"
                        "- C:\\Users\\Lucas\\Documents\\db2026\\\n"
                        "- Ou na pasta data/ do projeto."
                    )
                    return
            except Exception as e:
                QMessageBox.warning(
                    self, 
                    "Erro", 
                    f"Não foi possível criar o banco de dados:\n{str(e)}\n\n"
                    "Verifique se o arquivo CSV está em:\n"
                    "- C:\\Users\\Lucas\\Documents\\db2026\\\n"
                    "- Ou na pasta data/ do projeto."
                )
                return
    
    def _search_players(self):
        """Busca players baseado no termo digitado."""
        search_term = self.player_combo.currentText().strip()
        
        # Desabilitar botão durante busca
        self.search_btn.setEnabled(False)
        self.search_btn.setText("Buscando...")
        
        try:
            players = self.analyzer.get_available_players(search_term)
            
            self.player_combo.clear()
            if players:
                # Se há muitos resultados, mostrar apenas os primeiros 100
                if len(players) > 100:
                    self.player_combo.addItems(players[:100])
                    QMessageBox.information(
                        self, 
                        "Info", 
                        f"Encontrados {len(players)} players. Mostrando os primeiros 100.\n"
                        "Digite mais caracteres para refinar a busca."
                    )
                else:
                    self.player_combo.addItems(players)
            else:
                QMessageBox.information(self, "Info", "Nenhum player encontrado.")
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Erro ao buscar players: {e}")
        finally:
            self.search_btn.setEnabled(True)
            self.search_btn.setText("Buscar")
    
    def _calculate(self):
        """Calcula análise da aposta."""
        player_name = self.player_combo.currentText().strip()
        stat = self.stat_combo.currentText()
        line = self.line_spin.value()
        odd_over = self.odd_over_spin.value()
        odd_under = self.odd_under_spin.value()
        n_recent = self.n_recent_spin.value()
        
        if not player_name:
            QMessageBox.warning(self, "Erro", "Selecione um player.")
            return
        
        # Desabilitar botão durante cálculo
        self.calculate_btn.setEnabled(False)
        self.calculate_btn.setText("Calculando...")
        
        # Executar em thread separada
        self.analysis_thread = PlayerAnalysisThread(
            self.analyzer, player_name, stat, line, odd_over, odd_under, n_recent
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
        
        # Formatar resultado
        output = []
        output.append("=" * 80)
        output.append(f"📊 {result['stat'].upper()} — {result['player_name']}")
        output.append("=" * 80)
        output.append("")
        
        if result.get("games_warning"):
            output.append(f"⚠️ {result['games_warning']}")
            output.append("")
        
        output.append(f"📈 Estatísticas dos últimos {result['games_found']} jogos:")
        output.append(f"   • Média: {result['mean']:.2f}")
        output.append(f"   • Mediana: {result['median']:.2f}")
        output.append(f"   • Desvio padrão: {result['std']:.2f}")
        output.append(f"   • Mínimo: {result['min']:.1f}")
        output.append(f"   • Máximo: {result['max']:.1f}")
        output.append("")
        
        output.append(f"📊 Distribuição em relação à linha {result['line']}:")
        output.append(f"   • OVER {result['line']}:  {result['over_count']} jogos ({result['prob_over']*100:.2f}%)")
        output.append(f"   • UNDER {result['line']}: {result['under_count']} jogos ({result['prob_under']*100:.2f}%)")
        output.append("")
        
        # Últimos valores (confronto: time vs adversário)
        output.append(f"📋 Últimos {min(10, len(result['last_values']))} valores:")
        for i, item in enumerate(result['last_values'], 1):
            val = item["value"]
            team = item.get("team", "—")
            opponent = item.get("opponent", "—")
            jogo = f"{team} vs {opponent}" if (team != "—" or opponent != "—") else "—"
            resultado = "✅ OVER" if val > result['line'] else "❌ UNDER" if val < result['line'] else "⚖️ EXATO"
            output.append(f"   {i}. {val:.1f} {resultado} — {jogo}")
        output.append("")
        
        output.append("=" * 80)
        output.append("💰 ANÁLISE DE VALOR ESPERADO (EV)")
        output.append("=" * 80)
        output.append("")
        output.append("📈 Probabilidades Empíricas:")
        output.append(f"   Prob. Over {result['line']}:  {result['prob_over']*100:.2f}%")
        output.append(f"   Prob. Under {result['line']}: {result['prob_under']*100:.2f}%")
        output.append("")
        output.append("💰 EV e Fair Odds (Formato Pinnacle):")
        output.append(f"   Over  {result['line']}: EV = {result['ev_over']:+.2f}u ({result['ev_over_pct']:+.2%}) | Fair = {result['fair_over']:.3f}")
        output.append(f"   Under {result['line']}: EV = {result['ev_under']:+.2f}u ({result['ev_under_pct']:+.2%}) | Fair = {result['fair_under']:.3f}")
        output.append("")
        
        # Recomendação
        if "OVER" in result['recommendation']:
            output.append(f"✅ {result['recommendation']}")
        elif "UNDER" in result['recommendation']:
            output.append(f"✅ {result['recommendation']}")
        else:
            output.append(f"❌ {result['recommendation']}")
        output.append("")
        
        # Comparação com odds justas
        output.append("📊 Comparação com Fair Odds:")
        if result['odd_over'] < result['fair_over']:
            diff_over = ((result['fair_over'] - result['odd_over']) / result['fair_over']) * 100
            output.append(f"   ⚠️ Over está {diff_over:.1f}% abaixo da odd justa (valor negativo)")
        else:
            diff_over = ((result['odd_over'] - result['fair_over']) / result['fair_over']) * 100
            output.append(f"   ✅ Over está {diff_over:.1f}% acima da odd justa (valor positivo)")
        
        if result['odd_under'] < result['fair_under']:
            diff_under = ((result['fair_under'] - result['odd_under']) / result['fair_under']) * 100
            output.append(f"   ⚠️ Under está {diff_under:.1f}% abaixo da odd justa (valor negativo)")
        else:
            diff_under = ((result['odd_under'] - result['fair_under']) / result['fair_under']) * 100
            output.append(f"   ✅ Under está {diff_under:.1f}% acima da odd justa (valor positivo)")
        
        # Exibir resultado
        self.results_text.setPlainText("\n".join(output))
        self.results_text.verticalScrollBar().setValue(0)
    
    def _on_analysis_error(self, error_msg):
        """Chamado quando há erro na análise."""
        self.calculate_btn.setEnabled(True)
        self.calculate_btn.setText("Calcular")
        QMessageBox.critical(self, "Erro", f"Erro ao calcular: {error_msg}")
