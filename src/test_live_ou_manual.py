"""
Teste manual mínimo do predictor live Over/Under:
1) Bug-kill: jogo lento (20 min, 7 kills, gold -2300) -> λ ~5.9, Under alto
2) Sanity: jogo rápido (20 min, 22 kills) -> λ alto (~10-16), cap não atrapalha
3) Stomp: gold alto, kills baixas (15 min, 6 kills, +6000) -> gold_alpha=0, λ baixo e capado
"""
import sys
import os

# Garantir que core seja importável (rodar de qualquer cwd)
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from core.lol.live_over_under import (
    LiveOverUnderPredictor,
    _select_checkpoint,
    KPM_CAP_FACTOR,
    MINUTES_LEFT_BASE,
    KPM_GOLD_THRESHOLD,
    KPM_LOW_THRESHOLD,
    K_NEGBIN_BY_CHECKPOINT,
)


def run(minute: float, kills_now: int, gold_diff: float, label: str, lines: list[float] = (28.5, 30.5, 31.5)):
    kpm = kills_now / minute if minute > 0 else 0
    checkpoint = _select_checkpoint(minute)
    minutes_left = max(5, MINUTES_LEFT_BASE - minute)
    cap_by_kpm = minutes_left * kpm * KPM_CAP_FACTOR
    gold_alpha = "0" if kpm < KPM_GOLD_THRESHOLD else "aplicado"
    draft_effect = "zero (kpm<0.5)" if kpm < KPM_LOW_THRESHOLD else "aplicado"

    pred = LiveOverUnderPredictor()
    lam = pred.predict_lambda(minute, kills_now, gold_diff, draft_multiplier=None)
    lam_with_draft = pred.predict_lambda(minute, kills_now, gold_diff, draft_multiplier=1.07)

    print(f"\n--- {label} ---")
    print(f"  minute={minute}  kills_now={kills_now}  gold_diff={gold_diff}")
    print(f"  kpm={kpm:.2f}  checkpoint={checkpoint}  minutes_left={minutes_left}")
    print(f"  cap_by_kpm={cap_by_kpm:.2f}  gold_alpha={gold_alpha}  draft={draft_effect}")
    print(f"  lam (sem draft) = {lam:.3f}   lam (draft 1.07) = {lam_with_draft:.3f}")
    for line in lines:
        p_over, p_under = pred.prob_over_under(kills_now, line, lam)
        print(f"  Linha {line}: P(Over)={p_over:.2%}  P(Under)={p_under:.2%}")
    return lam


CENARIOS_TELA_MANUAL = [
    (15, 3, 0, "15min, 3 kills (seu)"),
    (20, 7, -2300, "20min, 7 kills (antigo morto)"),
    (20, 12, 0, "20min, 12 kills (meio termo)"),
    (20, 22, 0, "20min, 22 kills (rapido)"),
    (25, 10, 0, "25min, 10 kills (morto tardio)"),
]
LINHAS_OU_PADRAO = [25.5, 28.5, 30.5, 33.5]


if __name__ == "__main__":
    if "cenarios" in sys.argv or "--5" in sys.argv:
        use_nb = "poisson" not in sys.argv
        print("=== 5 cenarios - Tela manual (NegBin = menos 0/100 rigido) ===\n" if use_nb else "=== 5 cenarios - Poisson ===\n")
        pred = LiveOverUnderPredictor()
        for minute, kills, gold, label in CENARIOS_TELA_MANUAL:
            lam = pred.predict_lambda(minute, kills, gold, None)
            total_esp = kills + lam
            checkpoint = _select_checkpoint(minute)
            k_nb = K_NEGBIN_BY_CHECKPOINT.get(checkpoint, 6)
            print(label)
            print("  Entrada: min=%s  kills=%s  gold_diff=%s" % (minute, kills, gold))
            print("  lambda = %.2f   total esperado = %.1f   (k NegBin=%s)" % (lam, total_esp, k_nb if use_nb else "-"))
            for line in LINHAS_OU_PADRAO:
                if use_nb:
                    p_o, p_u = pred.prob_over_under_nb(kills, line, lam, k_nb)
                else:
                    p_o, p_u = pred.prob_over_under(kills, line, lam)
                print("  Linha %s: P(Over)=%s  P(Under)=%s" % (line, "%.1f%%" % (p_o * 100), "%.1f%%" % (p_u * 100)))
            print("")
        sys.exit(0)

    print("=== Teste manual Live Over/Under (tabelas + cap contextual + gold/draft condicionados) ===\n")

    # 1) Bug-kill: jogo lento
    lam1 = run(20.0, 7, -2300, "1) Bug-kill (jogo lento)", lines=[28.5, 30.5, 31.5])
    expected_cap = 13 * 0.35 * 1.3
    ok1 = lam1 <= 6.5 and lam1 >= 4.0  # ~5.9, margem
    print(f"  Esperado: lam ~5.9 (cap {expected_cap:.2f}). OK={ok1} (lam in [4, 6.5])")

    # 2) Sanity: jogo rápido
    lam2 = run(20.0, 22, 0, "2) Sanity (jogo rápido)", lines=[35.5, 40.5])
    ok2 = lam2 >= 10 and lam2 <= 20
    print(f"  Esperado: lam ~10-16, cap nao corta. OK={ok2} (lam in [10, 20])")

    # 3) Stomp: gold alto, kills baixas
    lam3 = run(15.0, 6, 6000, "3) Stomp (gold alto, kpm baixo)", lines=[20.5, 25.5])
    ok3 = lam3 <= 10  # gold não deve inflar
    print(f"  Esperado: gold_alpha=0, lam baixo e capado. OK={ok3} (lam <= 10)")

    print("\n--- Resumo ---")
    print(f"  Teste 1 (bug-kill): {'PASS' if ok1 else 'FAIL'}")
    print(f"  Teste 2 (sanity):   {'PASS' if ok2 else 'FAIL'}")
    print(f"  Teste 3 (stomp):    {'PASS' if ok3 else 'FAIL'}")
