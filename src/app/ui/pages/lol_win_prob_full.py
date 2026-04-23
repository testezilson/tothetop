"""
Página da calculadora Win Probability Full-Game: draft prior + gold @10/@15/@20.
Meta-modelo que combina prior do draft com estado do jogo (apenas ligas MAJOR).
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFormLayout, QSpinBox, QMessageBox, QTextEdit, QDoubleSpinBox
)
from PySide6.QtCore import Qt, QThread, Signal
from core.lol.win_prob_full import FullGameWinProbCalculator


class TrainFullModelThread(QThread):
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, calculator):
        super().__init__()
        self.calculator = calculator

    def run(self):
        try:
            from core.lol.compare import LoLCompareAnalyzer
            analyzer = LoLCompareAnalyzer()
            analyzer.load_data()
            metrics = self.calculator.train_and_save(analyzer=analyzer)
            self.finished.emit(metrics)
        except Exception as e:
            self.error.emit(str(e))


class LoLWinProbFullPage(QWidget):
    """Página Win Prob Full-Game: prior draft + gold @10, @15, @20."""

    def __init__(self):
        super().__init__()
        self.calculator = FullGameWinProbCalculator()
        self.train_thread = None
        self._init_ui()
        self._update_status()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Prior do draft
        prior_group = QGroupBox("Prior do draft (Time 1)")
        prior_layout = QFormLayout()
        self.draft_prior_spin = QDoubleSpinBox()
        self.draft_prior_spin.setRange(1, 99)
        self.draft_prior_spin.setDecimals(1)
        self.draft_prior_spin.setValue(50.0)
        self.draft_prior_spin.setSuffix(" %")
        self.draft_prior_spin.setToolTip("Deve ser igual ao 'Pré-jogo' da aba Prob. de Vitória para o mesmo draft. Ao abrir esta aba depois de calcular lá, o valor é preenchido automaticamente.")
        prior_layout.addRow("Prior draft (Time 1):", self.draft_prior_spin)
        prior_group.setLayout(prior_layout)
        layout.addWidget(prior_group)

        # Estado: gold @10, @15, @20
        state_group = QGroupBox("Estado do jogo (gold diff Time 1 − Time 2)")
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
        state_group.setLayout(state_layout)
        layout.addWidget(state_group)

        btn_layout = QHBoxLayout()
        self.calc_btn = QPushButton("Calcular probabilidade")
        self.calc_btn.clicked.connect(self._on_calculate)
        btn_layout.addWidget(self.calc_btn)
        self.train_btn = QPushButton("Treinar modelo (CSV)")
        self.train_btn.setToolTip("Requer draft prior calibrado e CSV com golddiffat10/15/20. Apenas MAJOR.")
        self.train_btn.clicked.connect(self._on_train)
        btn_layout.addWidget(self.train_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        result_group = QGroupBox("Resultado")
        result_layout = QVBoxLayout()
        self.result_label = QLabel("—")
        self.result_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        result_layout.addWidget(self.result_label)
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setMaximumHeight(120)
        result_layout.addWidget(self.results_text)
        result_group.setLayout(result_layout)
        layout.addWidget(result_group)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.status_label)
        layout.addStretch()

    def _update_status(self):
        csv_path = self.calculator.get_csv_path()
        if csv_path:
            self.status_label.setText(f"CSV: {csv_path}")
        else:
            self.status_label.setText("CSV do Oracle não encontrado (db2026 ou data/).")
        if self.calculator.ensure_model():
            self.status_label.setText(self.status_label.text() + "  |  Modelo full-game carregado.")
        else:
            self.status_label.setText(self.status_label.text() + "  |  Treine o modelo (e calibre o draft prior antes).")

    def _on_calculate(self):
        if not self.calculator.ensure_model():
            QMessageBox.warning(
                self, "Modelo não disponível",
                "Treine o modelo primeiro (e calibre o draft prior na aba Comparar Composições)."
            )
            return
        p_draft = self.draft_prior_spin.value() / 100.0
        g10 = self.gold_10_spin.value()
        g15 = self.gold_15_spin.value()
        g20 = self.gold_20_spin.value()
        prob = self.calculator.predict(p_draft, g10, g15, g20)
        if prob is None:
            self.result_label.setText("Erro ao calcular.")
            self.results_text.setPlainText("Não foi possível obter a probabilidade.")
            return
        pct_t1 = prob * 100
        pct_t2 = (1.0 - prob) * 100
        self.result_label.setText(f"Time 1: {pct_t1:.1f}%  |  Time 2: {pct_t2:.1f}%")
        self.results_text.setPlainText(
            f"Prior draft: Time 1 {p_draft*100:.1f}%  |  Time 2 {(1-p_draft)*100:.1f}%\n"
            f"Gold @10: {g10:+d}  @15: {g15:+d}  @20: {g20:+d}\n\n"
            "Modelo: regressão logística (logit(p_draft) + gold_diff_10/15/20). Apenas MAJOR."
        )

    def _on_train(self):
        self.train_btn.setEnabled(False)
        self.train_btn.setText("Treinando...")
        self.train_thread = TrainFullModelThread(self.calculator)
        self.train_thread.finished.connect(self._on_train_finished)
        self.train_thread.error.connect(self._on_train_error)
        self.train_thread.start()

    def _on_train_finished(self, metrics):
        self.train_btn.setEnabled(True)
        self.train_btn.setText("Treinar modelo (CSV)")
        if metrics.get("error"):
            QMessageBox.warning(self, "Erro no treino", metrics["error"])
            return
        brier = metrics.get("brier_score")
        reliability = metrics.get("reliability_bins") or []
        msg = (
            f"Amostras: {metrics.get('n_samples', 0)}\n"
            f"  Vitórias: {metrics.get('n_wins', 0)}  |  Derrotas: {metrics.get('n_losses', 0)}\n\n"
            f"Acurácia treino: {metrics.get('train_accuracy', 0)*100:.2f}%\n"
            f"Acurácia teste: {metrics.get('test_accuracy', 0)*100:.2f}%"
        )
        if brier is not None:
            msg += f"\n\nBrier score (teste): {brier:.4f}"
        if reliability:
            msg += "\n\nReliability bins (teste):"
            for center, mean_pred, mean_actual, count in reliability:
                msg += f"\n  [{center:.2f}] pred={mean_pred:.2f} real={mean_actual:.2f} n={count}"
        coefs = self.calculator.get_coefficients()
        if coefs:
            msg += "\n\nCoeficientes (positivo → mais assoc. a vitória Time 1):"
            for name, c in coefs:
                msg += f"\n  {name}: {c:+.4f}"
        QMessageBox.information(self, "Modelo full-game treinado", msg)
        self._update_status()

    def _on_train_error(self, err):
        self.train_btn.setEnabled(True)
        self.train_btn.setText("Treinar modelo (CSV)")
        QMessageBox.critical(self, "Erro", err)
        self._update_status()

    def set_draft_prior_pct(self, pct):
        """Preenche o prior do draft (0..100). Usado para auto-preenchimento da aba Comparar."""
        if pct is not None and 1 <= pct <= 99:
            self.draft_prior_spin.setValue(float(pct))

    def apply_shared_draft_prior(self):
        """Preenche o prior do draft com o valor da última comparação (aba Comparar), se houver."""
        mw = self.window()
        if mw is not None and hasattr(mw, "app_state"):
            pct = mw.app_state.get("draft_prior_pct")
            self.set_draft_prior_pct(pct)
