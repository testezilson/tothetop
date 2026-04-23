"""
Página da calculadora Win Probability @20 ou @25 min (só gold diff).
Uma aba "Win Prob @20" e uma "Win Prob @25" usam esta mesma página com minute=20 ou 25.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFormLayout, QSpinBox, QMessageBox, QTextEdit
)
from PySide6.QtCore import Qt, QThread, Signal
from core.lol.win_prob_mid import WinProbMidCalculator


class TrainModelThread(QThread):
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


class LoLWinProbMidPage(QWidget):
    """Página Win Prob @20 ou @25 (gold diff apenas). minute=20 ou 25."""

    def __init__(self, minute):
        super().__init__()
        assert minute in (20, 25)
        self.minute = minute
        self.calculator = WinProbMidCalculator(minute)
        self.train_thread = None
        self._init_ui()
        self._update_status()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        m = self.minute

        state_group = QGroupBox(f"Estado @{m} min (perspectiva do Time 1)")
        state_layout = QFormLayout()
        self.gold_diff_spin = QSpinBox()
        self.gold_diff_spin.setRange(-30000, 30000)
        self.gold_diff_spin.setSingleStep(100)
        self.gold_diff_spin.setValue(0)
        self.gold_diff_spin.setToolTip(f"Diferença de ouro Time 1 − Time 2 aos {m} min")
        state_layout.addRow(f"Gold Diff @{m}:", self.gold_diff_spin)
        state_group.setLayout(state_layout)
        layout.addWidget(state_group)

        btn_layout = QHBoxLayout()
        self.calc_btn = QPushButton("Calcular probabilidade")
        self.calc_btn.clicked.connect(self._on_calculate)
        btn_layout.addWidget(self.calc_btn)
        self.train_btn = QPushButton("Treinar modelo (CSV)")
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
        self.results_text.setMaximumHeight(100)
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
            self.status_label.setText(self.status_label.text() + "  |  Modelo carregado.")

    def _on_calculate(self):
        if not self.calculator.ensure_model():
            QMessageBox.warning(
                self, "Modelo não disponível",
                "Treine o modelo primeiro (botão 'Treinar modelo') ou verifique o CSV."
            )
            return
        gold = self.gold_diff_spin.value()
        prob = self.calculator.predict(gold)
        if prob is None:
            self.result_label.setText("Erro ao calcular.")
            self.results_text.setPlainText("Não foi possível obter a probabilidade.")
            return
        pct = prob * 100
        self.result_label.setText(f"Probabilidade de vitória (Time 1): {pct:.1f}%")
        self.results_text.setPlainText(
            f"Gold Diff @{self.minute}: {gold:+d}\n\n"
            f"Modelo: regressão logística (só gold diff @{self.minute} min)."
        )

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
            msg += "\n\nCoeficientes:"
            for name, c in coefs:
                msg += f"\n  {name}: {c:+.4f}"

        QMessageBox.information(self, f"Modelo treinado @{self.minute} min", msg)
        self._update_status()

    def _on_train_error(self, err):
        self.train_btn.setEnabled(True)
        self.train_btn.setText("Treinar modelo (CSV)")
        QMessageBox.critical(self, "Erro", err)
        self._update_status()
