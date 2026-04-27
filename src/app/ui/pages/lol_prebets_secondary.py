"""
Página de Pré-bets Secundárias do LoL (kills, torres, dragons, barons, gamelength).
UI: configuração no topo; resultados em HUD (duas colunas) + resumo H2H/EV.
"""
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QDoubleSpinBox,
    QSpinBox,
    QMessageBox,
    QCheckBox,
    QFrame,
    QScrollArea,
    QGridLayout,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QThread, Signal, QLocale
from core.lol.prebets_secondary import LoLSecondaryBetsAnalyzer
from app.ui.pages.lol_prebets_hud import build_prebets_hud


class FlexibleDoubleSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox que aceita tanto vírgula quanto ponto como separador decimal."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        self.lineEdit().textEdited.connect(self._on_text_edited)

    def _on_text_edited(self, text):
        if "," in text:
            normalized = text.replace(",", ".")
            cursor_pos = self.lineEdit().cursorPosition()
            self.lineEdit().blockSignals(True)
            self.lineEdit().setText(normalized)
            self.lineEdit().setCursorPosition(cursor_pos)
            self.lineEdit().blockSignals(False)

    def valueFromText(self, text):
        if isinstance(text, str):
            text = text.replace(",", ".")
        return super().valueFromText(text)

    def validate(self, text, pos):
        if isinstance(text, str):
            normalized_text = text.replace(",", ".")
        else:
            normalized_text = text
        return super().validate(normalized_text, pos)


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
                self.use_h2h,
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
        self.setObjectName("LoLPrebetsRoot")
        try:
            self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        except Exception:
            pass
        main = QVBoxLayout(self)
        main.setContentsMargins(8, 8, 8, 8)
        main.setSpacing(8)

        # —— Topo: configuração ——
        top = QFrame()
        top.setObjectName("prebetsConfig")
        top.setStyleSheet(
            """
            QFrame#prebetsConfig {
                background: #1f2937;
                border: 1px solid #374151;
                border-radius: 8px;
            }
            QLabel { color: #d1d5db; }
            """
        )
        top_l = QVBoxLayout(top)
        top_l.setContentsMargins(12, 10, 12, 10)
        title = QLabel("Seleção e parâmetros")
        title.setStyleSheet("font-weight: 700; font-size: 14px; color: #e5e7eb;")
        top_l.addWidget(title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)

        self.team1_combo = QComboBox()
        self.team1_combo.setEditable(True)
        self.team2_combo = QComboBox()
        self.team2_combo.setEditable(True)
        self.stat_combo = QComboBox()
        self.stat_combo.addItems(
            [
                "kills",
                "towers",
                "dragons",
                "barons",
                "gamelength",
                "first dragon",
                "first tower",
                "first herald",
            ]
        )
        self.stat_combo.currentTextChanged.connect(self._on_stat_changed)

        self.line_spin = FlexibleDoubleSpinBox()
        self.line_spin.setMinimum(0.0)
        self.line_spin.setMaximum(1000.0)
        self.line_spin.setDecimals(1)
        self.line_spin.setValue(25.5)
        self.odd_over_spin = QDoubleSpinBox()
        self.odd_over_spin.setMinimum(1.01)
        self.odd_over_spin.setMaximum(100.0)
        self.odd_over_spin.setDecimals(2)
        self.odd_over_spin.setValue(1.90)
        self.odd_under_spin = QDoubleSpinBox()
        self.odd_under_spin.setMinimum(1.01)
        self.odd_under_spin.setMaximum(100.0)
        self.odd_under_spin.setDecimals(2)
        self.odd_under_spin.setValue(1.90)
        self.limit_spin = QSpinBox()
        self.limit_spin.setMinimum(1)
        self.limit_spin.setMaximum(100)
        self.limit_spin.setValue(10)
        self.h2h_months_spin = QSpinBox()
        self.h2h_months_spin.setMinimum(1)
        self.h2h_months_spin.setMaximum(24)
        self.h2h_months_spin.setValue(3)
        self.use_h2h_check = QCheckBox("Incluir peso H2H")
        self.use_h2h_check.setChecked(False)

        r = 0
        grid.addWidget(QLabel("Time 1"), r, 0)
        grid.addWidget(self.team1_combo, r, 1)
        grid.addWidget(QLabel("Time 2"), r, 2)
        grid.addWidget(self.team2_combo, r, 3)
        r += 1
        grid.addWidget(QLabel("Estatística"), r, 0)
        grid.addWidget(self.stat_combo, r, 1)
        grid.addWidget(QLabel("Jogos recentes"), r, 2)
        grid.addWidget(self.limit_spin, r, 3)
        r += 1
        grid.addWidget(QLabel("Linha (mercado)"), r, 0)
        grid.addWidget(self.line_spin, r, 1)
        grid.addWidget(QLabel("Meses H2H"), r, 2)
        grid.addWidget(self.h2h_months_spin, r, 3)
        r += 1
        grid.addWidget(QLabel("Odd over"), r, 0)
        grid.addWidget(self.odd_over_spin, r, 1)
        grid.addWidget(self.use_h2h_check, r, 2, 1, 2)
        r += 1
        grid.addWidget(QLabel("Odd under"), r, 0)
        grid.addWidget(self.odd_under_spin, r, 1)

        top_l.addLayout(grid)
        row_btn = QHBoxLayout()
        self.analyze_btn = QPushButton("  Analisar  ")
        self.analyze_btn.setObjectName("btnAnalyze")
        self.analyze_btn.setCursor(Qt.PointingHandCursor)
        self.analyze_btn.clicked.connect(self._calculate)
        self.clear_btn = QPushButton("  Limpar resultados  ")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self._clear_results)
        row_btn.addWidget(self.analyze_btn)
        row_btn.addWidget(self.clear_btn)
        row_btn.addStretch(1)
        top_l.addLayout(row_btn)
        main.addWidget(top)

        # —— Resultados (scroll) ——
        self._scroll = QScrollArea()
        self._scroll.setObjectName("prebetsScrollArea")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._hud_host = QWidget()
        self._hud_host.setObjectName("prebetsHudHost")
        self._hud_layout = QVBoxLayout(self._hud_host)
        self._hud_layout.setContentsMargins(0, 4, 0, 0)
        self._scroll.setWidget(self._hud_host)
        self._scroll.viewport().setStyleSheet("background-color: #0e1117;")
        self._hud_host.setStyleSheet("background-color: #0e1117;")
        try:
            self._scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        except Exception:
            pass
        main.addWidget(self._scroll, 1)
        self._clear_results()

    def _clear_results(self) -> None:
        while self._hud_layout.count():
            it = self._hud_layout.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        ph = QLabel("Execute «Analisar» para ver a HUD com fair odds, EV e contexto por time.")
        ph.setStyleSheet("color: #9ca3af; padding: 20px; background: transparent;")
        self._hud_layout.addWidget(ph)

    def _load_data(self):
        db_path = self.analyzer.get_db_path()
        if db_path is None:
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
                        "Coloque o CSV (Oracle's Elixir) em data/ ou em Documents/db2026.",
                    )
                    return
            except Exception as e:
                QMessageBox.warning(self, "Erro", f"Não foi possível criar o banco de dados:\n{str(e)}")
                return
        try:
            teams = self.analyzer.get_available_teams()
            if teams:
                self.team1_combo.addItems([""] + teams)
                self.team2_combo.addItems([""] + teams)
            else:
                QMessageBox.warning(
                    self, "Aviso", "Banco encontrado, mas nenhum time na tabela. Verifique o CSV/DB."
                )
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Erro ao carregar times:\n{str(e)}")

    def _stat_to_internal(self, display_stat):
        mapping = {
            "first dragon": "firstdragon",
            "first tower": "firsttower",
            "first herald": "firstherald",
        }
        return mapping.get(display_stat, display_stat)

    def _on_stat_changed(self, text):
        is_first = text in ("first dragon", "first tower", "first herald")
        self.line_spin.setEnabled(not is_first)
        if is_first:
            self.line_spin.setValue(0.5)
        if is_first:
            self.odd_over_spin.setToolTip("Odd para o Time 1 conquistar o objetivo")
            self.odd_under_spin.setToolTip("Odd para o Time 2 conquistar o objetivo")
        else:
            self.odd_over_spin.setToolTip("")
            self.odd_under_spin.setToolTip("")

    def _calculate(self):
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
        self.analyze_btn.setEnabled(False)
        self.analyze_btn.setText("A analisar…")
        h2h_months = self.h2h_months_spin.value()
        use_h2h = self.use_h2h_check.isChecked()
        self._pending_analysis = (team1, team2, stat)
        self.analysis_thread = SecondaryAnalysisThread(
            self.analyzer,
            team1,
            team2,
            stat,
            line,
            odd_over,
            odd_under,
            limit_games,
            h2h_months,
            use_h2h,
        )
        self.analysis_thread.finished.connect(self._on_analysis_finished)
        self.analysis_thread.error.connect(self._on_analysis_error)
        self.analysis_thread.start()

    def _on_analysis_finished(self, result):
        self.analyze_btn.setEnabled(True)
        self.analyze_btn.setText("  Analisar  ")
        if result is None:
            QMessageBox.warning(self, "Erro", "Não foi possível calcular a análise.")
            return
        if "error" in result:
            QMessageBox.warning(self, "Erro", str(result.get("error", "Erro")))
            return
        pending = getattr(self, "_pending_analysis", None)
        if pending is not None:
            req_team1, req_team2, req_stat = pending
            if (result.get("team1"), result.get("team2"), result.get("stat")) != (req_team1, req_team2, req_stat):
                return
        # Limpar e mostrar HUD
        while self._hud_layout.count():
            it = self._hud_layout.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self._hud_layout.addWidget(build_prebets_hud(result))
        self._scroll.verticalScrollBar().setValue(0)

    def _on_analysis_error(self, error_msg):
        self.analyze_btn.setEnabled(True)
        self.analyze_btn.setText("  Analisar  ")
        QMessageBox.critical(self, "Erro", f"Erro ao calcular: {error_msg}")
