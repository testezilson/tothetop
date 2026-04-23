#!/usr/bin/env python3
"""
Sanity check das features do dota_live_snapshots.

Valida: gold_diff_now, kills_now, towers, roshan, consistência interna.
Opcionalmente busca OpenDota para verificar gold_adv em partidas reais.

Uso:
  python scripts/dota_live/sanity_check.py
  python scripts/dota_live/sanity_check.py --verify-gold 5
  python scripts/dota_live/sanity_check.py --db data/dota_opendota_leagues.db --snapshots data/dota_live_snapshots.csv
"""
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "dota_opendota_leagues.db"
SNAPSHOTS_PATH = PROJECT_ROOT / "data" / "dota_live_snapshots.csv"
CHECKPOINTS = [10, 15, 20, 25]


def _load_db_gold_and_objectives(conn, match_ids: list[int]) -> dict:
    """Retorna {match_id: (gold_adv, objectives)}."""
    cur = conn.execute("""
        SELECT match_id, radiant_gold_adv, objectives
        FROM dota_matches_stratz
        WHERE match_id IN ({})
    """.format(",".join("?" * len(match_ids))), match_ids)
    out = {}
    for row in cur.fetchall():
        mid, gold_json, obj_json = row[0], row[1], row[2]
        gold = json.loads(gold_json) if gold_json else []
        obj = json.loads(obj_json) if obj_json else []
        out[mid] = (gold, obj)
    return out


def run_internal_checks(df: pd.DataFrame) -> dict:
    """Checks de consistência interna."""
    issues = []
    stats = {}

    # kills_now <= total_final (total = kills_now + kills_remaining)
    total_final = df["kills_now"] + df["kills_remaining"]
    bad_kills = (df["kills_now"] > total_final) | (df["kills_now"] < 0)
    if bad_kills.any():
        issues.append(f"kills_now fora de [0, total_final]: {bad_kills.sum()} linhas")
    stats["total_final_mean"] = total_final.mean()
    stats["total_final_min"] = total_final.min()
    stats["total_final_max"] = total_final.max()

    # kpm plausível (0.1 a 3.0)
    bad_kpm = (df["kpm_now"] < 0) | (df["kpm_now"] > 4)
    if bad_kpm.any():
        issues.append(f"kpm_now fora de [0, 4]: {bad_kpm.sum()} linhas")

    # gold_diff plausível (-60k a +60k)
    bad_gold = (df["gold_diff_now"].abs() > 70000)
    if bad_gold.any():
        issues.append(f"gold_diff_now |x| > 70k: {bad_gold.sum()} linhas")
    stats["gold_diff_mean"] = df["gold_diff_now"].mean()
    stats["gold_diff_std"] = df["gold_diff_now"].std()

    # towers 0-11 cada, total 0-22
    bad_towers = (df["towers_total_alive"] < 0) | (df["towers_total_alive"] > 22)
    if bad_towers.any():
        issues.append(f"towers_total_alive fora de [0,22]: {bad_towers.sum()} linhas")

    # roshan 0-5 tipicamente
    bad_roshan = (df["roshan_kills_so_far"] < 0) | (df["roshan_kills_so_far"] > 6)
    if bad_roshan.any():
        issues.append(f"roshan_kills_so_far fora de [0,6]: {bad_roshan.sum()} linhas")

    return {"issues": issues, "stats": stats, "ok": len(issues) == 0}


def run_gold_index_check(df: pd.DataFrame, db_path: Path, n_samples: int = 20) -> dict:
    """
    Compara gold_diff_now do snapshot com gold_adv do DB.
    Testa se índice minute ou minute-1 está correto.
    """
    conn = sqlite3.connect(db_path)
    sample_ids = df["match_id"].drop_duplicates().sample(min(n_samples, df["match_id"].nunique()), random_state=42)
    db_data = _load_db_gold_and_objectives(conn, sample_ids.tolist())
    conn.close()

    results = []
    for mid in sample_ids:
        if mid not in db_data:
            continue
        gold_adv, _ = db_data[mid]
        rows = df[df["match_id"] == mid]
        for _, r in rows.iterrows():
            m = int(r["minute"])
            gold_snap = r["gold_diff_now"]
            val_at_m = gold_adv[m] if len(gold_adv) > m and isinstance(gold_adv[m], (int, float)) else None
            val_at_m1 = gold_adv[m - 1] if m > 0 and len(gold_adv) > m - 1 and isinstance(gold_adv[m - 1], (int, float)) else None
            match_m = val_at_m is not None and abs(gold_snap - val_at_m) < 1
            match_m1 = val_at_m1 is not None and abs(gold_snap - val_at_m1) < 1
            results.append({
                "match_id": mid,
                "minute": m,
                "gold_snapshot": gold_snap,
                "gold_adv[m]": val_at_m,
                "gold_adv[m-1]": val_at_m1,
                "match_index_m": match_m,
                "match_index_m1": match_m1,
            })

    if not results:
        return {"ok": None, "message": "Nenhum dado para comparar", "samples": []}

    rdf = pd.DataFrame(results)
    match_m = rdf["match_index_m"].sum()
    match_m1 = rdf["match_index_m1"].sum()
    total = len(rdf)
    return {
        "ok": match_m == total or match_m1 == total,
        "match_index_minute": match_m,
        "match_index_minute_minus_1": match_m1,
        "total": total,
        "samples": results[:10],
        "conclusion": "gold_adv[minute] correto" if match_m == total else (
            "gold_adv[minute-1] correto" if match_m1 == total else "Índice incerto - verificar manualmente"
        ),
    }


def run_opendota_verify(db_path: Path, n_matches: int = 3) -> None:
    """
    Opcional: busca OpenDota para partidas e compara gold.
    Requer requests e rede.
    """
    try:
        import requests
    except ImportError:
        print("  (requests não instalado - pulando verificação via OpenDota)")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "SELECT match_id FROM dota_matches_stratz WHERE duration > 600 LIMIT ?",
        (n_matches * 2,),
    )
    ids = [r[0] for r in cur.fetchall()]
    conn.close()

    api = "https://api.opendota.com/api"
    for mid in ids[:n_matches]:
        try:
            r = requests.get(f"{api}/matches/{mid}", timeout=10)
            if r.status_code != 200:
                continue
            m = r.json()
            gold = m.get("radiant_gold_adv") or []
            print(f"\n  Match {mid}: gold_adv length={len(gold)}")
            for cp in CHECKPOINTS:
                v = gold[cp] if len(gold) > cp else None
                v1 = gold[cp - 1] if cp > 0 and len(gold) > cp - 1 else None
                print(f"    min {cp}: gold_adv[{cp}]={v}, gold_adv[{cp-1}]={v1}")
        except Exception as e:
            print(f"  Match {mid}: erro {e}")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--snapshots", type=Path, default=SNAPSHOTS_PATH)
    parser.add_argument("--verify-gold", type=int, default=0, metavar="N",
                        help="Busca N partidas no OpenDota para verificar gold (0=desligado)")
    args = parser.parse_args()

    if not args.snapshots.exists():
        print(f"Erro: {args.snapshots} não encontrado. Rode build_snapshots.py primeiro.")
        sys.exit(1)

    df = pd.read_csv(args.snapshots)
    print("=" * 60)
    print("Sanity Check - Dota Live Snapshots")
    print("=" * 60)
    print(f"Snapshots: {len(df)} linhas, {df['match_id'].nunique()} partidas")
    print()

    # 1. Consistência interna
    print("1. Consistência interna")
    res = run_internal_checks(df)
    for k, v in res["stats"].items():
        print(f"   {k}: {v:.2f}" if isinstance(v, float) else f"   {k}: {v}")
    if res["issues"]:
        for i in res["issues"]:
            print(f"   [!] {i}")
    else:
        print("   [OK] Sem problemas de consistencia")
    print()

    # 2. Gold index (snapshot vs DB)
    print("2. Gold index (snapshot vs DB)")
    if args.db.exists():
        gold_res = run_gold_index_check(df, args.db, n_samples=30)
        if gold_res.get("ok") is not None:
            print(f"   match gold_adv[minute]: {gold_res.get('match_index_minute', 0)}/{gold_res.get('total', 0)}")
            print(f"   match gold_adv[minute-1]: {gold_res.get('match_index_minute_minus_1', 0)}/{gold_res.get('total', 0)}")
            print(f"   Conclusão: {gold_res.get('conclusion', '?')}")
            if gold_res.get("samples"):
                print("   Amostra (primeiras 3):")
                for s in gold_res["samples"][:3]:
                    print(f"     match={s['match_id']} min={s['minute']} snap={s['gold_snapshot']} adv[m]={s['gold_adv[m]']} adv[m-1]={s['gold_adv[m-1]']}")
        else:
            print(f"   {gold_res.get('message', 'Sem dados')}")
    else:
        print("   (DB não encontrado - pulando)")
    print()

    # 3. Verificação OpenDota (opcional)
    if args.verify_gold > 0 and args.db.exists():
        print("3. Verificação OpenDota (gold_adv bruto)")
        run_opendota_verify(args.db, args.verify_gold)
    else:
        print("3. Verificação OpenDota: --verify-gold N para habilitar")

    print()
    print("Fim do sanity check.")


if __name__ == "__main__":
    main()
