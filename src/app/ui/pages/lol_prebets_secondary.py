"""
Página de Pré-bets Secundárias do LoL (kills, torres, dragons, barons, gamelength).
"""
import re
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QLineEdit, QTextEdit, QGroupBox, QFormLayout,
    QDoubleSpinBox, QSpinBox, QMessageBox, QCheckBox
)
from PySide6.QtCore import Qt, QThread, Signal, QLocale
from PySide6.QtGui import QDoubleValidator
from core.lol.prebets_secondary import LoLSecondaryBetsAnalyzer


def _abbrev_team(name, max_chars=3):
    """Sigla do time: primeiras letras de cada palavra, até max_chars. Ex: 'CTBC Flying Oyster' -> 'CFO'."""
    if not name or not str(name).strip():
        return "—"
    words = re.sub(r"\s+", " ", str(name).strip()).split()
    if not words:
        return "—"
    out = "".join(w[0].upper() for w in words if w)[:max_chars]
    return out or "—"


def _format_value(val, stat):
    """Para gamelength: minutos decimais -> MM:SS. Para outros: inteiro."""
    try:
        v = float(val)
    except (TypeError, ValueError):
        return str(val)
    if stat and str(stat).lower() == "gamelength":
        m = int(v)
        s = int(round((v - m) * 60))
        if s >= 60:
            s, m = 0, m + 1
        return f"{m}:{s:02d}"
    return str(int(round(v)))


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
            # Contar quantas vírgulas foram substituídas antes da posição do cursor
            commas_before_cursor = text[:cursor_pos].count(',')
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


class SecondaryAnalysisThread(QThread):
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


class LoLSecondaryBetsPage(QWidget):
    """Página de análise de pré-bets secundárias do LoL."""
    
    def __init__(self):
        super().__init__()
        self.analyzer = LoLSecondaryBetsAnalyzer()
        self.analysis_thread = None
        
        self._init_ui()
        self._load_data()
    
    def _init_ui(self):
        """Inicializa a interface."""
        layout = QVBoxLayout(self)
        
        # Grupo de seleção
        selection_group = QGroupBox("Seleção de Jogo")
        selection_layout = QFormLayout()
        
        # Time 1
        self.team1_combo = QComboBox()
        self.team1_combo.setEditable(True)
        selection_layout.addRow("Time 1:", self.team1_combo)
        
        # Time 2
        self.team2_combo = QComboBox()
        self.team2_combo.setEditable(True)
        selection_layout.addRow("Time 2:", self.team2_combo)
        
        # Estatística
        self.stat_combo = QComboBox()
        self.stat_combo.addItems([
            "kills", "towers", "dragons", "barons", "gamelength",
            "first dragon", "first tower", "first herald"
        ])
        self.stat_combo.currentTextChanged.connect(self._on_stat_changed)
        selection_layout.addRow("Estatística:", self.stat_combo)
        
        selection_group.setLayout(selection_layout)
        layout.addWidget(selection_group)
        
        # Grupo de aposta
        bet_group = QGroupBox("Dados da Aposta")
        bet_layout = QFormLayout()
        
        # Linha - usar campo customizado que aceita vírgula e ponto
        self.line_spin = FlexibleDoubleSpinBox()
        self.line_spin.setMinimum(0.0)
        self.line_spin.setMaximum(1000.0)
        self.line_spin.setDecimals(1)
        self.line_spin.setValue(25.5)
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
        self.limit_spin = QSpinBox()
        self.limit_spin.setMinimum(1)
        self.limit_spin.setMaximum(100)
        self.limit_spin.setValue(10)
        bet_layout.addRow("Jogos recentes:", self.limit_spin)
        
        bet_group.setLayout(bet_layout)
        layout.addWidget(bet_group)
        
        # Grupo de H2H
        h2h_group = QGroupBox("Filtros H2H")
        h2h_layout = QFormLayout()
        
        # Meses de histórico H2H
        self.h2h_months_spin = QSpinBox()
        self.h2h_months_spin.setMinimum(1)
        self.h2h_months_spin.setMaximum(24)
        self.h2h_months_spin.setValue(3)
        h2h_layout.addRow("Meses de histórico H2H:", self.h2h_months_spin)
        
        # Incluir peso H2H
        self.use_h2h_check = QCheckBox()
        self.use_h2h_check.setChecked(False)
        h2h_layout.addRow("Incluir peso H2H:", self.use_h2h_check)
        
        h2h_group.setLayout(h2h_layout)
        layout.addWidget(h2h_group)
        
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
    
    def _stat_to_internal(self, display_stat):
        """Converte estatística exibida para nome interno."""
        mapping = {
            "first dragon": "firstdragon",
            "first tower": "firsttower",
            "first herald": "firstherald",
        }
        return mapping.get(display_stat, display_stat)
    
    def _on_stat_changed(self, text):
        """Quando muda estatística: desabilitar Linha para first objectives (usa 0.5 fixo)."""
        is_first = text in ("first dragon", "first tower", "first herald")
        self.line_spin.setEnabled(not is_first)
        if is_first:
            self.line_spin.setValue(0.5)
        # Tooltips para first stats
        if is_first:
            self.odd_over_spin.setToolTip("Odd para Time 1 conquistar o objetivo")
            self.odd_under_spin.setToolTip("Odd para Time 2 conquistar o objetivo")
        else:
            self.odd_over_spin.setToolTip("")
            self.odd_under_spin.setToolTip("")
    
    def _calculate(self):
        """Calcula análise da aposta."""
        team1 = self.team1_combo.currentText().strip()
        team2 = self.team2_combo.currentText().strip()
        stat = self._stat_to_internal(self.stat_combo.currentText())
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
        
        # Guardar requisição atual para ignorar resultados de execuções antigas (condição de corrida)
        self._pending_analysis = (team1, team2, stat)
        
        # Executar em thread separada
        self.analysis_thread = SecondaryAnalysisThread(
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
        
        # Ignorar resultado de uma execução antiga (outra thread terminou depois e sobrescreveria o stat errado)
        pending = getattr(self, "_pending_analysis", None)
        if pending is not None:
            req_team1, req_team2, req_stat = pending
            if (result.get("team1"), result.get("team2"), result.get("stat")) != (req_team1, req_team2, req_stat):
                return
        
        # Formatar resultado
        output = []
        is_first = result.get("is_first_stat", False)
        stat_display = result['stat'].replace("firstdragon", "first dragon").replace("firsttower", "first tower").replace("firstherald", "first herald")
        
        output.append("=" * 80)
        output.append(f"📊 {stat_display.upper()} — {result['team1']} vs {result['team2']}")
        output.append("=" * 80)
        output.append("")
        
        # Estatísticas por time
        if is_first:
            output.append("📉 Taxa de conquista por time (qual time pegou o objetivo):")
        else:
            output.append("📉 Estatísticas por time:")
        output.append("")
        output.append(f"🔵 {result['team1']}")
        if is_first:
            output.append(f"• Taxa: {result['mean_team1']*100:.1f}% ({result['team1_over']}/{result['team1_games']} jogos pegou)")
        else:
            output.append(f"• Média: {result['mean_team1']:.2f} ({result['team1_games']} jogos)")
            if result['team1_games'] > 0:
                output.append(f"• UNDER: {result['team1_under']} jogos ({result['team1_under']/result['team1_games']*100:.2f}%)")
                output.append(f"• OVER:  {result['team1_over']} jogos ({result['team1_over']/result['team1_games']*100:.2f}%)")
        output.append("")
        output.append(f"🔴 {result['team2']}")
        if is_first:
            output.append(f"• Taxa: {result['mean_team2']*100:.1f}% ({result['team2_over']}/{result['team2_games']} jogos pegou)")
        else:
            output.append(f"• Média: {result['mean_team2']:.2f} ({result['team2_games']} jogos)")
            if result['team2_games'] > 0:
                output.append(f"• UNDER: {result['team2_under']} jogos ({result['team2_under']/result['team2_games']*100:.2f}%)")
                output.append(f"• OVER:  {result['team2_over']} jogos ({result['team2_over']/result['team2_games']*100:.2f}%)")
        # Últimos 10 valores em duas colunas: sigla do adversário — valor (MM:SS para gamelength)
        items1 = (result.get("last_values_team1") or [])[:10]
        items2 = (result.get("last_values_team2") or [])[:10]
        stat_key = result.get("stat", "")
        if items1 or items2:
            output.append("")
            output.append("📋 Últimos 10 valores")
            col_width = 18  # espaço para "ABB - MM:SS" ou "ABB - 123"
            for i in range(max(len(items1), len(items2))):
                left = ""
                if i < len(items1):
                    it = items1[i]
                    opp = _abbrev_team(it.get("opponent", "—"))
                    val = _format_value(it.get("value", it.get("total", "—")), stat_key)
                    left = f"  {opp} - {val}"
                right = ""
                if i < len(items2):
                    it = items2[i]
                    opp = _abbrev_team(it.get("opponent", "—"))
                    val = _format_value(it.get("value", it.get("total", "—")), stat_key)
                    right = f"{opp} - {val}"
                line = left.ljust(col_width) + right if right else left
                output.append(line)
            output.append("")
        
        # Estatísticas combinadas
        total_games = result['team1_games'] + result['team2_games']
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
        
        # H2H
        if result.get('use_h2h'):
            output.append("=" * 80)
            output.append("HISTORICO H2H")
            output.append("=" * 80)
            output.append("")
            if result.get('h2h_games', 0) == 0:
                output.append("Nenhum jogo H2H encontrado no periodo.")
            elif result.get('h2h_rate') is not None:
                output.append(f"Jogos H2H encontrados: {result['h2h_games']}")
                if is_first:
                    output.append(f"Time 1 pegou: {result['h2h_over']} jogos ({result['h2h_rate']*100:.2f}%)")
                    output.append(f"Time 2 pegou: {result['h2h_under']} jogos ({(1-result['h2h_rate'])*100:.2f}%)")
                else:
                    output.append(f"Media H2H: {result['h2h_mean']:.2f}")
                    output.append(f"OVER {result['line']}: {result['h2h_over']} jogos ({result['h2h_rate']*100:.2f}%)")
                    output.append(f"UNDER {result['line']}: {result['h2h_under']} jogos ({(1-result['h2h_rate'])*100:.2f}%)")
                output.append("")
                output.append(f"Peso H2H: {result['w_h2h']*100:.1f}% | Peso Forma: {result['w_form']*100:.1f}%")
            output.append("")
        
        # Probabilidades
        output.append("=" * 80)
        output.append("📈 PROBABILIDADES")
        output.append("=" * 80)
        output.append("")
        if result.get('use_h2h') and result.get('h2h_rate') is not None:
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
        
        # EV e Fair Odds
        output.append("=" * 80)
        output.append("💰 EV E FAIR ODDS (Formato Pinnacle)")
        output.append("=" * 80)
        output.append("")
        if is_first:
            output.append(f"Time 1: EV = {result['ev_over']:+.2f}u ({result['ev_over_pct']:+.2%}) | Fair = {result['fair_over']:.3f}")
            output.append(f"Time 2: EV = {result['ev_under']:+.2f}u ({result['ev_under_pct']:+.2%}) | Fair = {result['fair_under']:.3f}")
        else:
            output.append(f"Over  {result['line']}: EV = {result['ev_over']:+.2f}u ({result['ev_over_pct']:+.2%}) | Fair = {result['fair_over']:.3f}")
            output.append(f"Under {result['line']}: EV = {result['ev_under']:+.2f}u ({result['ev_under_pct']:+.2%}) | Fair = {result['fair_under']:.3f}")
        output.append("")
        
        # Recomendação
        if "OVER" in result['recommendation']:
            output.append(f"✅ {result['recommendation']}")
        elif "UNDER" in result['recommendation']:
            output.append(f"✅ {result['recommendation']}")
        else:
            output.append(f"❌ {result['recommendation']}")
        
        # Exibir resultado
        self.results_text.setPlainText("\n".join(output))
        self.results_text.verticalScrollBar().setValue(0)
    
    def _on_analysis_error(self, error_msg):
        """Chamado quando há erro na análise."""
        self.calculate_btn.setEnabled(True)
        self.calculate_btn.setText("Calcular")
        QMessageBox.critical(self, "Erro", f"Erro ao calcular: {error_msg}")
