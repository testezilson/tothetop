"""
Página da calculadora de probabilidade de vitória no Early Game (até 15 min).
Nova aba no app: Early-Game Win Prob.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFormLayout, QSpinBox, QComboBox, QMessageBox, QTextEdit,
    QCheckBox, QDoubleSpinBox
)
from PySide6.QtCore import Qt, QThread, Signal
from core.lol.win_prob_early import EarlyGameWinProbCalculator
from core.lol.draft_prior import combine_log_odds, weight_for_minute


class TrainModelThread(QThread):
    """Thread para treinar o modelo sem travar a UI."""
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, calculator):
        super().__init__()
        self.calculator = calculator

    def run(self):
        try:
            metrics = self.calculator.train_and_save()
            self.finished.emit(metrics)
        except Exception as e:
            self.error.emit(str(e))


class LoLWinProbEarlyPage(QWidget):
    """Página da calculadora Early-Game Win Probability."""

    def __init__(self):
        super().__init__()
        self.calculator = EarlyGameWinProbCalculator()
        self.train_thread = None
        self._init_ui()
        self._update_status()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # ---- Estado do jogo aos 15 min ----
        state_group = QGroupBox("Estado aos 15 min (perspectiva do Time 1)")
        state_layout = QFormLayout()

        self.gold_diff_spin = QSpinBox()
        self.gold_diff_spin.setRange(-20000, 20000)
        self.gold_diff_spin.setSingleStep(100)
        self.gold_diff_spin.setValue(0)
        self.gold_diff_spin.setToolTip("Diferença de ouro Time 1 − Time 2 aos 15 min (ex: +1500 = Time 1 na frente)")
        state_layout.addRow("Gold Diff @15:", self.gold_diff_spin)

        self.first_tower_combo = QComboBox()
        self.first_tower_combo.addItems(["Nenhum", "Time 1", "Time 2"])
        self.first_tower_combo.setToolTip("Quem destruiu a primeira torre")
        state_layout.addRow("First Tower:", self.first_tower_combo)

        self.first_dragon_combo = QComboBox()
        self.first_dragon_combo.addItems(["Nenhum", "Time 1", "Time 2"])
        self.first_dragon_combo.setToolTip("Quem pegou o primeiro dragão")
        state_layout.addRow("First Dragon:", self.first_dragon_combo)

        state_group.setLayout(state_layout)
        layout.addWidget(state_group)

        # ---- Prior do draft (opcional) ----
        prior_group = QGroupBox("Prior do draft (opcional)")
        prior_layout = QFormLayout()
        self.use_draft_prior_check = QCheckBox("Combinar com prior do draft")
        self.use_draft_prior_check.setToolTip("Use o valor da aba 'Comparar Composições' (Prob. calibrada) ou estime o prior pré-jogo.")
        self.use_draft_prior_check.setChecked(False)
        prior_layout.addRow(self.use_draft_prior_check)
        self.draft_prior_spin = QDoubleSpinBox()
        self.draft_prior_spin.setRange(1, 99)
        self.draft_prior_spin.setDecimals(1)
        self.draft_prior_spin.setValue(50.0)
        self.draft_prior_spin.setSuffix(" %")
        self.draft_prior_spin.setToolTip("Prob. pré-jogo do Time 1 (ex.: da aba Comparar Composições)")
        prior_layout.addRow("Prior draft (Time 1):", self.draft_prior_spin)
        prior_group.setLayout(prior_layout)
        layout.addWidget(prior_group)

        # ---- Botões ----
        btn_layout = QHBoxLayout()
        self.calc_btn = QPushButton("Calcular probabilidade")
        self.calc_btn.clicked.connect(self._on_calculate)
        btn_layout.addWidget(self.calc_btn)

        self.train_btn = QPushButton("Treinar modelo (CSV)")
        self.train_btn.clicked.connect(self._on_train)
        self.train_btn.setToolTip("Treina a regressão logística com o CSV do Oracle's Elixir")
        btn_layout.addWidget(self.train_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # ---- Resultado ----
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

        # Status do modelo
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.status_label)
        layout.addStretch()

    def apply_shared_draft_prior(self):
        """Preenche o prior do draft com o valor da última comparação (aba Comparar), se houver."""
        mw = self.window()
        if mw is not None and hasattr(mw, "app_state"):
            pct = mw.app_state.get("draft_prior_pct")
            if pct is not None and 1 <= pct <= 99:
                self.draft_prior_spin.setValue(float(pct))

    def _update_status(self):
        csv_path = self.calculator.get_csv_path()
        if csv_path:
            self.status_label.setText(f"CSV: {csv_path}")
        else:
            self.status_label.setText("CSV do Oracle não encontrado (db2026 ou data/).")
        if self.calculator.ensure_model():
            self.status_label.setText(self.status_label.text() + "  |  Modelo carregado.")

    def _first_tower_value(self):
        """Retorna 1 se Time 1, 0 se Nenhum ou Time 2."""
        return 1 if self.first_tower_combo.currentIndex() == 1 else 0

    def _first_dragon_value(self):
        return 1 if self.first_dragon_combo.currentIndex() == 1 else 0

    def _on_calculate(self):
        if not self.calculator.ensure_model():
            QMessageBox.warning(
                self,
                "Modelo não disponível",
                "Treine o modelo primeiro (botão 'Treinar modelo') ou verifique se o CSV do Oracle está em db2026 ou data/."
            )
            return

        gold = self.gold_diff_spin.value()
        ft = self._first_tower_value()
        fd = self._first_dragon_value()

        p_state = self.calculator.predict(gold, ft, fd)
        if p_state is None:
            self.result_label.setText("Erro ao calcular.")
            self.results_text.setPlainText("Não foi possível obter a probabilidade.")
            return

        use_prior = self.use_draft_prior_check.isChecked()
        p_draft = self.draft_prior_spin.value() / 100.0 if use_prior else None
        w = weight_for_minute(15)

        if use_prior and p_draft is not None:
            p_final = combine_log_odds(p_draft, p_state, w=w)
            pct_t1 = p_final * 100
            pct_t2 = (1.0 - p_final) * 100
            self.result_label.setText(f"Time 1: {pct_t1:.1f}%  |  Time 2: {pct_t2:.1f}%")
            lines = [
                f"  p_draft (pré-jogo):  Time 1 {p_draft*100:.1f}%  |  Time 2 {(1-p_draft)*100:.1f}%",
                f"  p_state (estado @15): Time 1 {p_state*100:.1f}%  |  Time 2 {(1-p_state)*100:.1f}%",
                f"  p_final (combinação, w_draft={w:.2f}): Time 1 {p_final*100:.1f}%  |  Time 2 {(1-p_final)*100:.1f}%",
                "",
                "Combinação: log-odds L_final = w·L(p_draft) + (1-w)·L(p_state); p_final = σ(L_final).",
            ]
        else:
            pct_t1 = p_state * 100
            pct_t2 = (1.0 - p_state) * 100
            self.result_label.setText(f"Time 1: {pct_t1:.1f}%  |  Time 2: {pct_t2:.1f}%")
            lines = []

        ft_label = self.first_tower_combo.currentText()
        fd_label = self.first_dragon_combo.currentText()
        lines = [
            "Estado early game:",
            f"  Gold Diff @15: {gold:+d}  |  First Tower: {ft_label}  |  First Dragon: {fd_label}",
            "",
        ] + lines + [
            "Modelo: regressão logística (gold@15 + first tower + first dragon).",
            "",
            "Dica: Marque 'Combinar com prior do draft' e use o % da aba Comparar Composições (Prob. calibrada).",
        ]
        self.results_text.setPlainText("\n".join(lines))

    def _on_train(self):
        self.train_btn.setEnabled(False)
        self.train_btn.setText("Treinando...")
        self.train_thread = TrainModelThread(self.calculator)
        self.train_thread.finished.connect(self._on_train_finished)
        self.train_thread.error.connect(self._on_train_error)
        self.train_thread.start()

    def _on_train_finished(self, metrics):
        self.train_btn.setEnabled(True)
        self.train_btn.setText("Treinar modelo (CSV)")
        if metrics.get("error"):
            QMessageBox.warning(self, "Erro no treino", metrics["error"])
            return
        n_wins = metrics.get("n_wins", 0)
        n_losses = metrics.get("n_losses", 0)
        brier = metrics.get("brier_score")
        reliability = metrics.get("reliability_bins") or []

        msg = (
            f"Amostras: {metrics.get('n_samples', 0)}\n"
            f"  Vitórias: {n_wins}  |  Derrotas: {n_losses}\n\n"
            f"Acurácia treino: {metrics.get('train_accuracy', 0)*100:.2f}%\n"
            f"Acurácia teste: {metrics.get('test_accuracy', 0)*100:.2f}%\n"
            f"ROC AUC: {metrics.get('roc_auc', 0):.3f}"
        )
        if brier is not None:
            msg += f"\n\nCalibração (teste):\n  Brier score: {brier:.4f} (menor = melhor)"
        if reliability:
            msg += "\n\n  Reliability bins (pred médio | real médio | n):"
            for center, mean_pred, mean_actual, count in reliability:
                msg += f"\n    [{center:.2f}] pred={mean_pred:.2f} real={mean_actual:.2f} n={count}"

        coefs = self.calculator.get_coefficients()
        if coefs:
            msg += "\n\nCoeficientes (positivo → mais assoc. a vitória):"
            for name, c in coefs:
                msg += f"\n  {name}: {c:+.4f}"
        QMessageBox.information(self, "Modelo treinado", msg)
        self._update_status()

    def _on_train_error(self, err):
        self.train_btn.setEnabled(True)
        self.train_btn.setText("Treinar modelo (CSV)")
        QMessageBox.critical(self, "Erro", err)
        self._update_status()
