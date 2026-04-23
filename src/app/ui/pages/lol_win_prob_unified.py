"""
Aba única de Probabilidade de Vitória: draft (10 campeões) + estado do jogo.
Um único botão "Calcular" mostra: pré-jogo (só draft), aos 15 min (só estado),
combinada (draft + estado) e vitória final (modelo full-game).
Evita trocar de abas e explica em português o que é cada número.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFormLayout, QSpinBox, QComboBox, QLineEdit,
    QMessageBox, QTextEdit, QScrollArea, QFrame
)
from PySide6.QtCore import Qt, QThread, Signal
from core.lol.compare import LoLCompareAnalyzer
from core.lol.draft_prior import combine_log_odds, weight_for_minute
from core.lol.win_prob_early import EarlyGameWinProbCalculator
from core.lol.win_prob_full import FullGameWinProbCalculator


class TrainEarlyThread(QThread):
    finished = Signal(dict)
    error = Signal(str)

    def run(self):
        try:
            calc = EarlyGameWinProbCalculator()
            m = calc.train_and_save()
            self.finished.emit(m)
        except Exception as e:
            self.error.emit(str(e))


class TrainFullGameThread(QThread):
    finished = Signal(dict)
    error = Signal(str)

    def run(self):
        try:
            from core.lol.compare import LoLCompareAnalyzer
            analyzer = LoLCompareAnalyzer()
            analyzer.load_data()
            calc = FullGameWinProbCalculator()
            m = calc.train_and_save(analyzer=analyzer)
            self.finished.emit(m)
        except Exception as e:
            self.error.emit(str(e))


class WinProbUnifiedThread(QThread):
    """Calcula draft + early + combinada + full-game em uma thread."""
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, league, comp1, comp2, gold_10, gold_15, gold_20, first_tower, first_dragon):
        super().__init__()
        self.league = league
        self.comp1 = comp1
        self.comp2 = comp2
        self.gold_10 = gold_10
        self.gold_15 = gold_15
        self.gold_20 = gold_20
        self.first_tower = first_tower
        self.first_dragon = first_dragon

    def run(self):
        try:
            analyzer = LoLCompareAnalyzer()
            if not analyzer.load_data():
                self.error.emit("Dados do comparador não carregados.")
                return
            result_compare = analyzer.compare_compositions(self.league, self.comp1, self.comp2)
            p_draft = result_compare.get("p_draft_calibrated")
            if p_draft is None:
                # Fallback: usar 50% ou score bruto como aproximação
                s1 = result_compare.get("factors1", {}).get("total_score", 50)
                s2 = result_compare.get("factors2", {}).get("total_score", 50)
                from core.lol.draft_prior import calibrated_draft_prob
                p_draft = calibrated_draft_prob(s1, s2)
            if p_draft is None:
                p_draft = 0.5

            early_calc = EarlyGameWinProbCalculator()
            early_calc.ensure_model()
            p_state = early_calc.predict(self.gold_15, self.first_tower, self.first_dragon)
            if p_state is None:
                p_state = 0.5

            w = weight_for_minute(15)
            p_combined = combine_log_odds(p_draft, p_state, w=w)

            full_calc = FullGameWinProbCalculator()
            p_full = None
            if full_calc.ensure_model():
                p_full = full_calc.predict(p_draft, self.gold_10, self.gold_15, self.gold_20)

            self.finished.emit({
                "p_draft": p_draft,
                "p_state": p_state,
                "p_combined": p_combined,
                "p_full": p_full,
                "winner": result_compare.get("winner", "—"),
                "difference": result_compare.get("difference", 0),
            })
        except Exception as e:
            self.error.emit(str(e))


class LoLWinProbUnifiedPage(QWidget):
    """
    Uma aba só: você preenche os 10 campeões + liga e o estado do jogo (ouro, objetivos).
    Um botão "Calcular" mostra todas as probabilidades com nomes claros em português.
    """

    def __init__(self):
        super().__init__()
        self.analyzer = LoLCompareAnalyzer()
        self.calc_thread = None
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ---- Explicação em português ----
        help_frame = QFrame()
        help_frame.setStyleSheet("QFrame { background-color: #f0f4f8; border-radius: 6px; padding: 4px; }")
        help_layout = QVBoxLayout(help_frame)
        help_title = QLabel("Como usar")
        help_title.setStyleSheet("font-weight: bold;")
        help_layout.addWidget(help_title)
        help_text = QLabel(
            "Preencha os 10 campeões (Time 1 e Time 2) e a liga. Depois preencha o estado do jogo "
            "(diferença de ouro, primeira torre/dragão). Clique em <b>Calcular</b> para ver:\n"
            "• <b>Pré-jogo</b> = chance do Time 1 ganhar só pelos campeões escolhidos (antes do jogo).\n"
            "• <b>Aos 15 min</b> = chance só pelo estado atual (ouro, objetivos).\n"
            "• <b>Combinada</b> = junção do draft com o estado aos 15 min.\n"
            "• <b>Vitória final</b> = modelo que usa draft + ouro @10/15/20 (se estiver treinado)."
        )
        help_text.setWordWrap(True)
        help_text.setTextFormat(Qt.TextFormat.RichText)
        help_layout.addWidget(help_text)
        layout.addWidget(help_frame)

        # ---- Draft: liga + 10 campeões ----
        draft_group = QGroupBox("1. Draft (campeões dos dois times)")
        draft_layout = QVBoxLayout()
        self.league_combo = QComboBox()
        self.league_combo.setEditable(True)
        draft_layout.addWidget(QLabel("Liga:"))
        draft_layout.addWidget(self.league_combo)

        self._team_picks = {}
        row_draft = QHBoxLayout()
        for side, label in [("1", "Time 1"), ("2", "Time 2")]:
            col = QVBoxLayout()
            col.addWidget(QLabel(label))
            self._team_picks[side] = []
            positions = ["Top", "Jungle", "Mid", "ADC", "Support"]
            for pos in positions:
                le = QLineEdit()
                le.setPlaceholderText(pos)
                col.addWidget(le)
                self._team_picks[side].append(le)
            row_draft.addLayout(col)
        draft_layout.addLayout(row_draft)
        draft_group.setLayout(draft_layout)
        layout.addWidget(draft_group)

        # ---- Estado do jogo ----
        state_group = QGroupBox("2. Estado do jogo (perspectiva do Time 1)")
        state_layout = QFormLayout()
        self.gold_10_spin = QSpinBox()
        self.gold_10_spin.setRange(-20000, 20000)
        self.gold_10_spin.setSingleStep(100)
        self.gold_10_spin.setValue(0)
        state_layout.addRow("Gold Diff @10:", self.gold_10_spin)
        self.gold_15_spin = QSpinBox()
        self.gold_15_spin.setRange(-20000, 20000)
        self.gold_15_spin.setSingleStep(100)
        self.gold_15_spin.setValue(0)
        state_layout.addRow("Gold Diff @15:", self.gold_15_spin)
        self.gold_20_spin = QSpinBox()
        self.gold_20_spin.setRange(-20000, 20000)
        self.gold_20_spin.setSingleStep(100)
        self.gold_20_spin.setValue(0)
        state_layout.addRow("Gold Diff @20:", self.gold_20_spin)
        self.first_tower_combo = QComboBox()
        self.first_tower_combo.addItems(["Nenhum", "Time 1", "Time 2"])
        state_layout.addRow("First Tower:", self.first_tower_combo)
        self.first_dragon_combo = QComboBox()
        self.first_dragon_combo.addItems(["Nenhum", "Time 1", "Time 2"])
        state_layout.addRow("First Dragon:", self.first_dragon_combo)
        state_group.setLayout(state_layout)
        layout.addWidget(state_group)

        # ---- Botões: Calcular e Treinar modelos ----
        btn_row = QHBoxLayout()
        self.calc_btn = QPushButton("Calcular probabilidades")
        self.calc_btn.setStyleSheet("font-weight: bold; min-height: 32px;")
        self.calc_btn.clicked.connect(self._on_calculate)
        btn_row.addWidget(self.calc_btn)
        btn_row.addStretch()
        self.train_early_btn = QPushButton("Treinar modelo Early (CSV)")
        self.train_early_btn.setToolTip("Regressão logística: gold@15 + first tower + first dragon → vitória")
        self.train_early_btn.clicked.connect(self._on_train_early)
        btn_row.addWidget(self.train_early_btn)
        self.train_full_btn = QPushButton("Treinar modelo Full-Game (CSV)")
        self.train_full_btn.setToolTip("Requer draft prior calibrado. logit(p_draft) + gold@10/15/20 → vitória final. MAJOR.")
        self.train_full_btn.clicked.connect(self._on_train_full)
        btn_row.addWidget(self.train_full_btn)
        layout.addLayout(btn_row)

        # ---- Resultado ----
        result_group = QGroupBox("Resultado (Time 1 vs Time 2)")
        result_layout = QVBoxLayout()
        self.result_big = QLabel("—")
        self.result_big.setStyleSheet("font-size: 20px; font-weight: bold;")
        self.result_big.setAlignment(Qt.AlignmentFlag.AlignCenter)
        result_layout.addWidget(self.result_big)
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMaximumHeight(220)
        result_layout.addWidget(self.result_text)
        result_group.setLayout(result_layout)
        layout.addWidget(result_group)

        # Status e dica
        self.status_label = QLabel("Dica: calibre o pré-jogo na aba 'Comparar Composições'. Treine os modelos acima para Early e Vitória final.")
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.status_label)
        layout.addStretch()

    def _on_train_early(self):
        self.train_early_btn.setEnabled(False)
        self.train_early_btn.setText("Treinando Early...")
        self._train_early_thread = TrainEarlyThread()
        self._train_early_thread.finished.connect(self._on_train_early_finished)
        self._train_early_thread.error.connect(self._on_train_early_error)
        self._train_early_thread.start()

    def _on_train_early_finished(self, metrics):
        self.train_early_btn.setEnabled(True)
        self.train_early_btn.setText("Treinar modelo Early (CSV)")
        if metrics.get("error"):
            QMessageBox.warning(self, "Treino Early", metrics["error"])
            return
        msg = f"Amostras: {metrics.get('n_samples', 0)}\nVitórias: {metrics.get('n_wins', 0)} | Derrotas: {metrics.get('n_losses', 0)}\n"
        msg += f"Acurácia teste: {metrics.get('test_accuracy', 0)*100:.2f}%\nBrier: {metrics.get('brier_score', 0):.4f}"
        QMessageBox.information(self, "Modelo Early treinado", msg)

    def _on_train_early_error(self, err):
        self.train_early_btn.setEnabled(True)
        self.train_early_btn.setText("Treinar modelo Early (CSV)")
        QMessageBox.critical(self, "Erro", err)

    def _on_train_full(self):
        self.train_full_btn.setEnabled(False)
        self.train_full_btn.setText("Treinando Full-Game...")
        self._train_full_thread = TrainFullGameThread()
        self._train_full_thread.finished.connect(self._on_train_full_finished)
        self._train_full_thread.error.connect(self._on_train_full_error)
        self._train_full_thread.start()

    def _on_train_full_finished(self, metrics):
        self.train_full_btn.setEnabled(True)
        self.train_full_btn.setText("Treinar modelo Full-Game (CSV)")
        if metrics.get("error"):
            QMessageBox.warning(self, "Treino Full-Game", metrics["error"])
            return
        msg = f"Amostras: {metrics.get('n_samples', 0)}\nVitórias: {metrics.get('n_wins', 0)} | Derrotas: {metrics.get('n_losses', 0)}\n"
        msg += f"Acurácia teste: {metrics.get('test_accuracy', 0)*100:.2f}%\nBrier: {metrics.get('brier_score', 0):.4f}"
        QMessageBox.information(self, "Modelo Full-Game treinado", msg)

    def _on_train_full_error(self, err):
        self.train_full_btn.setEnabled(True)
        self.train_full_btn.setText("Treinar modelo Full-Game (CSV)")
        QMessageBox.critical(self, "Erro", err)

    def _load_data(self):
        try:
            if not self.analyzer.load_data():
                return
            leagues = self.analyzer.get_available_leagues()
            if leagues:
                self.league_combo.clear()
                self.league_combo.addItems(leagues)
                if "MAJOR" in leagues:
                    self.league_combo.setCurrentText("MAJOR")
        except Exception:
            pass

    def _get_comp(self, side):
        picks = self._team_picks.get(side, [])
        return [p.text().strip() for p in picks]

    def _on_calculate(self):
        league = self.league_combo.currentText().strip()
        if not league:
            QMessageBox.warning(self, "Aviso", "Escolha uma liga.")
            return
        comp1 = self._get_comp("1")
        comp2 = self._get_comp("2")
        if len(comp1) != 5 or not all(comp1):
            QMessageBox.warning(self, "Aviso", "Preencha os 5 campeões do Time 1.")
            return
        if len(comp2) != 5 or not all(comp2):
            QMessageBox.warning(self, "Aviso", "Preencha os 5 campeões do Time 2.")
            return

        ft = 1 if self.first_tower_combo.currentIndex() == 1 else 0
        fd = 1 if self.first_dragon_combo.currentIndex() == 1 else 0

        self.calc_btn.setEnabled(False)
        self.calc_btn.setText("Calculando...")
        self.calc_thread = WinProbUnifiedThread(
            league, comp1, comp2,
            self.gold_10_spin.value(), self.gold_15_spin.value(), self.gold_20_spin.value(),
            ft, fd
        )
        self.calc_thread.finished.connect(self._on_finished)
        self.calc_thread.error.connect(self._on_error)
        self.calc_thread.start()

    def _on_finished(self, data):
        self.calc_btn.setEnabled(True)
        self.calc_btn.setText("Calcular probabilidades")
        p_draft = data["p_draft"]
        p_state = data["p_state"]
        p_combined = data["p_combined"]
        p_full = data.get("p_full")

        # Atualizar prior compartilhado: ao abrir Full-Game ou Early-Game, o prior será este (evita 66.8% vs 54.4% diferente)
        mw = self.window()
        if mw is not None and hasattr(mw, "app_state"):
            mw.app_state["draft_prior_pct"] = round(p_draft * 100, 1)

        p_combined_t2 = (1.0 - p_combined) * 100
        p_combined_t1 = p_combined * 100
        self.result_big.setText(f"Combinada: Time 1 {p_combined_t1:.1f}%  |  Time 2 {p_combined_t2:.1f}%")
        lines = [
            f"Pré-jogo (só pelos campeões):     Time 1 {p_draft*100:.1f}%  |  Time 2 {(1-p_draft)*100:.1f}%  — antes do jogo.",
            f"Aos 15 min (só pelo estado):       Time 1 {p_state*100:.1f}%  |  Time 2 {(1-p_state)*100:.1f}%  — ouro, primeira torre/dragão.",
            f"Combinada (draft + estado @15):   Time 1 {p_combined*100:.1f}%  |  Time 2 {(1-p_combined)*100:.1f}%  — número principal para early game.",
        ]
        if p_full is not None:
            lines.append(f"Vitória final (draft + @10/15/20): Time 1 {p_full*100:.1f}%  |  Time 2 {(1-p_full)*100:.1f}%  — previsão de quem ganha o jogo.")
        else:
            lines.append("Vitória final: — (treine o modelo abaixo com 'Treinar modelo Full-Game (CSV)').")
        self.result_text.setPlainText("\n".join(lines))

    def _on_error(self, msg):
        self.calc_btn.setEnabled(True)
        self.calc_btn.setText("Calcular probabilidades")
        QMessageBox.warning(self, "Erro", msg)
        self.result_big.setText("—")
        self.result_text.setPlainText("")
