"""
Valida o predictor Live Over/Under com todos os jogos da liga MAJOR na base.

Para cada (jogo, checkpoint): prediz lambda (kills restantes esperados), compara com
kills_future real. Reporta: linha de kills esperada (kills_now + lambda), total real,
e se o jogo ficou numa faixa proxima ao esperado (ex.: +/- 2, 3, 4 kills).
"""
import os
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

import numpy as np
import pandas as pd

from core.shared.utils import MAJOR_LEAGUES
from core.lol.live_over_under import LiveOverUnderPredictor
from train_live_over_under import build_checkpoint_dataset, ORACLE_ELIXIR_CSV


def main():
    if not os.path.exists(ORACLE_ELIXIR_CSV):
        print(f"CSV nao encontrado: {ORACLE_ELIXIR_CSV}")
        print("  Use o mesmo CSV OraclesElixir do treino (killsat10/15/20/25, golddiffat*, etc.).")
        return

    print("Carregando dataset de checkpoints (OraclesElixir)...")
    df = build_checkpoint_dataset(ORACLE_ELIXIR_CSV)
    df_major = df[
        df["league"].astype(str).str.upper().isin([lg.upper() for lg in MAJOR_LEAGUES])
    ].copy()
    if df_major.empty:
        print("Nenhum jogo MAJOR encontrado no CSV.")
        return

    n_rows = len(df_major)
    n_games = df_major["gameid"].nunique()
    print(f"  Total: {n_rows} linhas (jogo x checkpoint) | {n_games} jogos MAJOR\n")

    pred = LiveOverUnderPredictor()
    expected_total = []
    actual_total = []
    lam_pred = []
    kills_future_actual = []
    minute_col = []
    kills_now_col = []

    for _, row in df_major.iterrows():
        minute = float(row["minute"])
        kills_now = float(row["kills_now"])
        gold_diff = float(row["gold_diff"])
        k_future = float(row["kills_future"])
        total = kills_now + k_future

        lam = pred.predict_lambda(minute, kills_now, gold_diff)
        exp_t = kills_now + lam

        minute_col.append(minute)
        kills_now_col.append(kills_now)
        lam_pred.append(lam)
        kills_future_actual.append(k_future)
        expected_total.append(exp_t)
        actual_total.append(total)

    df_major = df_major.copy()
    df_major["lam_pred"] = lam_pred
    df_major["expected_total"] = expected_total
    df_major["actual_total"] = actual_total
    df_major["error_remaining"] = np.array(lam_pred) - np.array(kills_future_actual)
    df_major["error_total"] = np.array(actual_total) - np.array(expected_total)

    # Metricas globais
    mae_remaining = np.abs(df_major["error_remaining"]).mean()
    mae_total = np.abs(df_major["error_total"]).mean()
    median_ae_total = np.median(np.abs(df_major["error_total"]))

    print("--- Faixa: total real dentro de X kills do total esperado ---")
    for band in [2, 3, 4, 5, 8, 10]:
        pct = (np.abs(df_major["error_total"]) <= band).mean() * 100
        print(f"  +/- {band} kills: {pct:.1f}%")

    print("\n--- Metricas globais (MAJOR) ---")
    print(f"  MAE (kills restantes): pred - real = {mae_remaining:.2f}")
    print(f"  MAE (total kills):     |actual - expected| = {mae_total:.2f}")
    print(f"  Mediana |erro total|:  {median_ae_total:.2f}")
    q25, q50, q75 = np.percentile(df_major["error_total"], [25, 50, 75])
    print(f"  Erro total (actual - expected): P25={q25:.1f}  P50={q50:.1f}  P75={q75:.1f}")

    # Por ritmo (kpm): em jogos ja rapidos o cap atrapalha menos
    df_major["kpm"] = df_major["kills_now"] / df_major["minute"]
    slow = df_major[df_major["kpm"] < 0.5]
    fast = df_major[df_major["kpm"] >= 0.5]
    if len(slow) > 0:
        print(f"\n  Jogos lentos (kpm < 0.5): N={len(slow)}  MAE(total)={np.abs(slow['error_total']).mean():.2f}  dentro+/-5: {(np.abs(slow['error_total']) <= 5).mean()*100:.1f}%")
    if len(fast) > 0:
        print(f"  Jogos rapidos (kpm >= 0.5): N={len(fast)}  MAE(total)={np.abs(fast['error_total']).mean():.2f}  dentro+/-5: {(np.abs(fast['error_total']) <= 5).mean()*100:.1f}%")

    # Por checkpoint
    print("\n--- Por checkpoint (minuto) ---")
    for t in [10, 15, 20, 25]:
        sub = df_major[df_major["minute"] == t]
        if sub.empty:
            continue
        mae_t = np.abs(sub["error_total"]).mean()
        for band in [2, 3, 4]:
            pct = (np.abs(sub["error_total"]) <= band).mean() * 100
            print(f"  min {t:2d}: N={len(sub):4d}  MAE(total)={mae_t:.2f}  dentro +/-{band}: {pct:.1f}%")

    # Resumo: linha esperada vs faixa real
    print("\n--- Linha esperada vs total real (amostra por checkpoint) ---")
    print("  checkpoint | kills_now | gold_diff | expected_total | actual_total | erro | na_faixa+/-3")
    np.random.seed(42)
    for t in [10, 15, 20, 25]:
        sub = df_major[df_major["minute"] == t]
        if sub.empty:
            continue
        sample = sub.sample(min(5, len(sub)))
        for _, r in sample.iterrows():
            faixa = "sim" if abs(r["error_total"]) <= 3 else "nao"
            print(f"  {int(r['minute']):2d}         | {int(r['kills_now']):2d}        | {r['gold_diff']:7.0f}   | {r['expected_total']:6.1f}         | {int(r['actual_total']):6.0f}       | {r['error_total']:+5.1f} | {faixa}")

    print("\nFim da validacao.")


if __name__ == "__main__":
    main()
