import hashlib
import importlib.util
import os
import shutil
import sqlite3
import subprocess
import sys
from typing import Any, List
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def _cyberscore_db_path() -> str:
    default = str(BASE_DIR / "data" / "cyberscore.db")
    return os.path.normpath(os.path.abspath(os.environ.get("CYBERSCORE_DB_PATH", default)))


def _db_snapshot_cyberscore(path: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "exists": False,
        "size": None,
        "sha256": None,
        "rows": None,
    }
    if not path or not os.path.isfile(path):
        return out
    out["exists"] = True
    out["size"] = os.path.getsize(path)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    out["sha256"] = h.hexdigest()
    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM matches")
        out["rows"] = int(cur.fetchone()[0])
        conn.close()
    except Exception:
        out["rows"] = None
    return out

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler
from lol_prebet_core import build_prebet_api_payload

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

class LolPrebetRequest(BaseModel):
    team1: str
    team2: str
    stat: str = "kills"
    line: float
    odd_over: float = 1.90
    odd_under: float = 1.90
    limit_games: int = 10
    h2h_months: int = 3
    use_h2h: bool = False


class LolPlayerPrebetRequest(BaseModel):
    player: str
    stat: str = "kills"
    line: float
    odd_over: float = 1.90
    odd_under: float = 1.90
    limit_games: int = 10


class LolDraftRequest(BaseModel):
    league: str = "MAJOR"
    threshold: float = 0.55
    team1_picks: List[str]
    team2_picks: List[str]


class DotaPrebetRequest(BaseModel):
    team1: str
    team2: str
    stat: str = "first_tower"
    line: float = 0.5
    odd_team1: float = 1.83
    odd_team2: float = 1.83
    limit_games: int = 15
    h2h_months: int = 3
    use_h2h: bool = False


class DotaDraftRequest(BaseModel):
    radiant_team: str = ""
    dire_team: str = ""
    limit_games: int = 15
    radiant_picks: List[str]
    dire_picks: List[str]


class FootballTeamPrebetRequest(BaseModel):
    team1_id: int
    team1_name: str
    team2_id: int
    team2_name: str
    stat: str = "total_cards"
    line: float = 4.5
    odd_over: float = 1.83
    odd_under: float = 1.83
    limit_games: int = 10
    h2h_months: int = 6
    use_h2h: bool = False
    referee_name: str = ""
    referee_sample_games: int = 10


class FootballPlayerPrebetRequest(BaseModel):
    team_id: int
    team_name: str
    player_id: int
    player_name: str
    stat: str = "shots_total"
    line: float = 1.5
    odd_over: float = 1.83
    odd_under: float = 1.83
    limit_games: int = 10


class DotaPrebetsUpdateRequest(BaseModel):
    team_id: str = ""


class DotaDraftLiveUpdateRequest(BaseModel):
    league_id: str
    league_name: str = ""
    opendota_api_key: str = ""

@app.post("/api/lol/prebets")
def lol_prebets(req: LolPrebetRequest):
    t1, t2 = (req.team1 or "").strip(), (req.team2 or "").strip()
    if not t1 or not t2:
        raise HTTPException(status_code=400, detail="Preencha os dois times.")
    if t1.lower() == t2.lower():
        raise HTTPException(status_code=400, detail="Os times devem ser diferentes.")
    try:
        return build_prebet_api_payload(
            t1,
            t2,
            req.stat,
            req.line,
            req.odd_over,
            req.odd_under,
            req.limit_games,
            req.h2h_months,
            req.use_h2h,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/lol/player-prebets")
def lol_player_prebets(req: LolPlayerPrebetRequest):
    try:
        from lol_player_prebet_core import build_player_prebet_api_payload

        return build_player_prebet_api_payload(
            player=req.player,
            stat=req.stat,
            line=req.line,
            odd_over=req.odd_over,
            odd_under=req.odd_under,
            limit_games=req.limit_games,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Erro na API: {e}")


@app.post("/api/lol/draft")
def lol_draft(req: LolDraftRequest):
    try:
        from lol_draft_core import build_lol_draft_payload

        return build_lol_draft_payload(
            league=req.league,
            threshold=req.threshold,
            team1_picks=req.team1_picks,
            team2_picks=req.team2_picks,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Erro na API: {e}")


@app.post("/api/dota/prebets")
def dota_prebets(req: DotaPrebetRequest):
    try:
        from dota_prebet_core import build_dota_prebet_payload

        return build_dota_prebet_payload(
            team1=req.team1,
            team2=req.team2,
            stat=req.stat,
            line=req.line,
            odd_team1=req.odd_team1,
            odd_team2=req.odd_team2,
            limit_games=req.limit_games,
            h2h_months=req.h2h_months,
            use_h2h=req.use_h2h,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Erro na API: {e}") from e


@app.get("/api/debug/dota-runtime")
def debug_dota_runtime(
    team1: str = "TEAM LIQUID",
    team2: str = "BETBOOM TEAM",
    stat: str = "first_tower",
    limit_games: int = 15,
):
    import hashlib
    import sqlite3

    from core.dota.prebets_secondary import (
        DotaSecondaryBetsAnalyzer,
        fetch_team_recent,
        get_dota_db_path,
    )
    from core.shared.paths import BASE_DIR as paths_base, path_in_data

    db_path = get_dota_db_path()

    def file_info(path: str | None) -> dict:
        if not path or not os.path.exists(path):
            return {"exists": False, "path": path}
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return {
            "exists": True,
            "size": os.path.getsize(path),
            "sha256": h.hexdigest(),
            "abs": os.path.abspath(path),
        }

    info = {
        "cwd": os.getcwd(),
        "BASE_DIR": str(paths_base),
        "DATA_DIR": path_in_data(""),
        "DOTA_DB_PATH_env": os.environ.get("DOTA_DB_PATH"),
        "db": file_info(db_path),
        "team1": team1,
        "team2": team2,
        "stat": stat,
        "limit_games": limit_games,
    }
    if not db_path:
        return info

    conn = sqlite3.connect(db_path)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(matches)").fetchall()]
        row_count = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
        analyzer = DotaSecondaryBetsAnalyzer()
        runtime = analyzer.analyze_bet(
            team1,
            team2,
            stat,
            0.5,
            1.83,
            1.83,
            limit_games=limit_games,
            h2h_months=3,
            use_h2h=False,
        )
        info.update(
            {
                "matches_rows": int(row_count),
                "columns": cols,
                "team1_recent_values": fetch_team_recent(conn, team1, stat, limit_games),
                "team2_recent_values": fetch_team_recent(conn, team2, stat, limit_games),
                "analysis": runtime,
            }
        )
    finally:
        conn.close()
    return jsonable_encoder(info)


@app.post("/api/dota/draft")
def dota_draft(req: DotaDraftRequest):
    try:
        from dota_draft_core import analyze_dota_draft

        return analyze_dota_draft(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Erro na API: {e}") from e


@app.post("/api/football/prebets/team")
def football_team_prebets(req: FootballTeamPrebetRequest):
    try:
        from football_prebet_core import build_football_team_prebet_payload

        return build_football_team_prebet_payload(
            team1_id=req.team1_id,
            team1_name=req.team1_name,
            team2_id=req.team2_id,
            team2_name=req.team2_name,
            stat=req.stat,
            line=req.line,
            odd_over=req.odd_over,
            odd_under=req.odd_under,
            limit_games=req.limit_games,
            h2h_months=req.h2h_months,
            use_h2h=req.use_h2h,
            referee_name=req.referee_name,
            referee_sample_games=req.referee_sample_games,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Erro na API: {e}") from e


@app.post("/api/football/prebets/player")
def football_player_prebets(req: FootballPlayerPrebetRequest):
    try:
        from football_prebet_core import build_football_player_prebet_payload

        return build_football_player_prebet_payload(
            team_id=req.team_id,
            team_name=req.team_name,
            player_id=req.player_id,
            player_name=req.player_name,
            stat=req.stat,
            line=req.line,
            odd_over=req.odd_over,
            odd_under=req.odd_under,
            limit_games=req.limit_games,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Erro na API: {e}") from e


@app.get("/api/football/search-teams")
def football_search_teams(q: str = ""):
    try:
        from football_prebet_core import search_football_teams

        return {"query": q, "teams": search_football_teams(q)}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Erro na API: {e}") from e


@app.get("/api/football/search-players")
def football_search_players(team_id: int, q: str = "", season: int | None = None):
    try:
        from football_prebet_core import search_football_players

        return {
            "query": q,
            "team_id": team_id,
            "season": season,
            "players": search_football_players(team_id, q, season),
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Erro na API: {e}") from e


@app.get("/api/debug/football-runtime")
def debug_football_runtime():
    from core.football.api_client import BASE_URL, FootballAPIClient
    from core.football.prebets_football import PLAYER_STATS, TEAM_STATS, default_api_season_year
    from core.shared.paths import path_in_data

    key_file = path_in_data("football_api_key.txt")
    client = FootballAPIClient()
    data = {
        "core_used": "core.football.prebets_football",
        "base_url": BASE_URL,
        "cwd": os.getcwd(),
        "BASE_DIR": str(BASE_DIR),
        "FOOTBALL_API_KEY_env": bool(os.environ.get("FOOTBALL_API_KEY")),
        "APISPORTS_KEY_env": bool(os.environ.get("APISPORTS_KEY")),
        "X_APISPORTS_KEY_env": bool(os.environ.get("X_APISPORTS_KEY")),
        "key_file": {
            "path": key_file,
            "exists": os.path.exists(key_file),
            "size": os.path.getsize(key_file) if os.path.exists(key_file) else None,
        },
        "has_key": client.has_key(),
        "default_season": default_api_season_year(),
        "team_stats": TEAM_STATS,
        "player_stats": PLAYER_STATS,
    }
    return JSONResponse(content=jsonable_encoder(data))


@app.post("/api/admin/update/lol-prebets")
def update_lol_prebets():
    return {
        "ok": True,
        "message": "Endpoint recebido.",
        "log": "Recebido: atualizar banco LoL Pré-bets. Execução real ainda não plugada.",
    }


@app.post("/api/admin/update/lol-draft")
def update_lol_draft():
    return {
        "ok": True,
        "message": "Endpoint recebido.",
        "log": "Recebido: atualizar Draft/Compare LoL. Execução real ainda não plugada.",
    }


@app.post("/api/admin/update/dota-prebets")
def update_dota_prebets(req: DotaPrebetsUpdateRequest):
    team_id = (req.team_id or "").strip()
    if not team_id:
        raise HTTPException(status_code=400, detail="team_id é obrigatório.")

    script_path = BASE_DIR / "scripts" / "import_cyberscore_completo.py"
    if not script_path.is_file():
        raise HTTPException(
            status_code=500,
            detail=f"Script não encontrado: {script_path}",
        )

    db_path = _cyberscore_db_path()
    db_before = _db_snapshot_cyberscore(db_path)
    data_dir = os.path.dirname(db_path)
    if data_dir:
        os.makedirs(data_dir, exist_ok=True)

    env = os.environ.copy()
    env["CYBERSCORE_DB_PATH"] = db_path
    env["SELENIUM_HEADLESS"] = "1"
    if "PYTHONUNBUFFERED" not in env:
        env["PYTHONUNBUFFERED"] = "1"

    timeout = int(os.environ.get("CYBERSCORE_IMPORT_TIMEOUT", "3600"))
    try:
        proc = subprocess.run(
            [sys.executable, "-u", str(script_path), team_id],
            cwd=str(BASE_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (proc.stdout or "") + ""
        err = (proc.stderr or "") + ""
        code = int(proc.returncode)
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") if isinstance(e.stdout, str) else str(e.stdout or "")
        err = (e.stderr or "") if isinstance(e.stderr, str) else str(e.stderr or "")
        err = (err or "") + f"\n[timeout após {timeout}s]"
        code = -1
    except Exception as e:
        out = ""
        err = str(e)
        code = -1

    db_after = _db_snapshot_cyberscore(db_path)
    body = {
        "ok": code == 0,
        "team_id": team_id,
        "db_before": db_before,
        "db_after": db_after,
        "stdout": out,
        "stderr": err,
        "returncode": code,
    }
    return JSONResponse(content=jsonable_encoder(body))


@app.post("/api/admin/update/dota-draft-live")
def update_dota_draft_live(req: DotaDraftLiveUpdateRequest):
    return {
        "ok": True,
        "message": "Endpoint recebido.",
        "league_id": req.league_id,
        "league_name": req.league_name,
        "has_opendota_key": bool(req.opendota_api_key),
        "log": "Recebido: atualizar Dota Draft Live. Execução real ainda não plugada.",
    }


@app.get("/api/debug/selenium-runtime")
def debug_selenium_runtime():
    which_chrome = shutil.which("google-chrome") or shutil.which("google-chrome-stable")
    which_chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    which_d = shutil.which("chromedriver")
    sel_spec = importlib.util.find_spec("selenium")
    return JSONResponse(
        content=jsonable_encoder(
            {
                "ok": True,
                "cwd": os.getcwd(),
                "BASE_DIR": str(BASE_DIR),
                "which_google_chrome": which_chrome,
                "which_chromium": which_chromium,
                "which_chromedriver": which_d,
                "selenium_import_ok": sel_spec is not None,
                "RAILWAY_ENVIRONMENT": bool(os.environ.get("RAILWAY_ENVIRONMENT")),
                "CYBERSCORE_DB_PATH": _cyberscore_db_path(),
            }
        )
    )


@app.get("/api/debug/update-runtime")
def debug_update_runtime():
    return {
        "ok": True,
        "message": "Update runtime disponível.",
        "cwd": os.getcwd(),
        "BASE_DIR": str(BASE_DIR),
        "endpoints": [
            "/api/admin/update/lol-prebets",
            "/api/admin/update/lol-draft",
            "/api/admin/update/dota-prebets",
            "/api/admin/update/dota-draft-live",
            "/api/debug/selenium-runtime",
        ],
    }


@app.get("/api/debug/dota-draft-runtime")
def debug_dota_draft_runtime(
    radiant_team: str = "Team Liquid",
    dire_team: str = "BetBoom Team",
    limit_games: int = 15,
    radiant_picks: str = "Medusa,Night Stalker,Tiny,Rubick,Clockwerk",
    dire_picks: str = "Windranger,Puck,Beastmaster,Hoodwink,Venomancer",
):
    import hashlib

    from core.dota.draft_testezudo import DotaDraftTestezudoAnalyzer
    from core.dota.prebets_secondary import get_dota_db_path
    from core.shared.paths import BASE_DIR as paths_base, path_in_data, path_in_models

    analyzer = DotaDraftTestezudoAnalyzer()
    filenames = [
        "models_dota_v2_7.pkl",
        "config_dota_v2_7.pkl",
        "trained_models_dota_v2.pkl",
        "scaler_dota_v2.pkl",
        "feature_columns_dota_v2.pkl",
        "hero_impacts_bayesian_single.pkl",
    ]

    def info(path: str | None) -> dict:
        if not path or not os.path.exists(path):
            return {"exists": False, "path": path}
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return {
            "exists": True,
            "size": os.path.getsize(path),
            "sha256": h.hexdigest(),
            "abs": os.path.abspath(path),
        }

    files = {name: info(analyzer._path(name)) for name in filenames}
    db_path = get_dota_db_path()
    load_ok = analyzer.load_models()
    radiant = [x.strip() for x in radiant_picks.split(",") if x.strip()]
    dire = [x.strip() for x in dire_picks.split(",") if x.strip()]
    analysis = None
    if load_ok:
        analysis = analyzer.analyze_draft(
            radiant,
            dire,
            radiant_team_name=None,
            dire_team_name=None,
            n_games=int(limit_games or 15),
        )
    team_factor = (analysis or {}).get("team_factor") or {}

    data = {
        "core_used": "draft_testezudo_v2_7",
        "cwd": os.getcwd(),
        "BASE_DIR": str(paths_base),
        "DATA_DIR": path_in_data(""),
        "MODELS_DIR": path_in_models(""),
        "DOTA_DRAFT_DIR_env": os.environ.get("DOTA_DRAFT_DIR"),
        "DOTA_DB_PATH_env": os.environ.get("DOTA_DB_PATH"),
        "db": info(db_path),
        "files": files,
        "load_models": load_ok,
        "last_error": analyzer.last_error,
        "heroes_count": len(analyzer.hero_impacts or {}) if load_ok else 0,
        "models_count": len(analyzer.models or {}) if load_ok else 0,
        "has_scaler": getattr(analyzer, "scaler", None) is not None,
        "request": {
            "radiant_team": radiant_team,
            "dire_team": dire_team,
            "limit_games": limit_games,
            "radiant_picks": radiant,
            "dire_picks": dire,
        },
        "global_mean": (analysis or {}).get("global_mean"),
        "draft_multiplier": (analysis or {}).get("draft_multiplier"),
        "draft_strength_multiplier": (analysis or {}).get("draft_strength_multiplier"),
        "feature_set": (analysis or {}).get("feature_set"),
        "min_games": (analysis or {}).get("min_games"),
        "radiant_total": (analysis or {}).get("radiant_total"),
        "dire_total": (analysis or {}).get("dire_total"),
        "draft_total": (analysis or {}).get("total_geral"),
        "estimated_kills": (analysis or {}).get("kills_estimadas"),
        "team_factor_used": False,
        "team_factor": team_factor or None,
        "weight_draft": 1.0,
        "weight_times": 0.0,
        "raw_predictions": (analysis or {}).get("predictions"),
        "lines_calculated": list(((analysis or {}).get("predictions") or {}).keys()),
        "analysis": analysis,
    }
    return JSONResponse(content=jsonable_encoder(data))


@app.post("/api/debug/draft-raw")
def debug_draft_raw(req: LolDraftRequest):
    try:
        from core.lol.draft import LoLDraftAnalyzer

        analyzer = LoLDraftAnalyzer()
        result = analyzer.analyze_draft(
            league=req.league,
            team1=req.team1_picks,
            team2=req.team2_picks,
            threshold=req.threshold,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Erro: {e}") from e
    if result is None:
        raise HTTPException(
            status_code=503,
            detail="analyze_draft retornou None (modelos/dados não carregaram?)",
        )
    return jsonable_encoder(result)


@app.get("/api/debug/draft-files")
def debug_draft_files():
    files = [
        "model_artifacts/trained_models_v3.pkl",
        "model_artifacts/scaler_v3.pkl",
        "model_artifacts/feature_columns_v3.pkl",
        "data/league_stats_v3.pkl",
        "data/champion_impacts.csv",
        "data/2026_LoL_esports_match_data_from_OraclesElixir.csv",
        "src/load_and_predict_v3.py",
    ]
    return {f: (BASE_DIR / f).is_file() for f in files}


@app.get("/api/debug/draft-env")
def debug_draft_env():
    import hashlib
    from core.shared.paths import BASE_DIR as paths_base, path_in_data, path_in_models
    from pathlib import Path

    path_root = Path(paths_base)
    rel_files = [
        "data/2026_LoL_esports_match_data_from_OraclesElixir.csv",
        "data/oracle_prepared.csv",
        "data/champion_impacts.csv",
        "data/league_stats_v3.pkl",
        "model_artifacts/trained_models_v3.pkl",
        "model_artifacts/scaler_v3.pkl",
        "model_artifacts/feature_columns_v3.pkl",
        "src/load_and_predict_v3.py",
        "core/lol/draft.py",
    ]

    def info(rel: str) -> dict:
        path = str(path_root / rel)
        if not os.path.exists(path):
            return {"exists": False, "path": path}

        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)

        return {
            "exists": True,
            "size": os.path.getsize(path),
            "sha256": h.hexdigest(),
            "abs": os.path.abspath(path),
        }

    return {
        "cwd": os.getcwd(),
        "BASE_DIR": str(paths_base),
        "data_dir": path_in_data(""),
        "models_dir": path_in_models(""),
        "files": {f: info(f) for f in rel_files},
    }


@app.get("/api/debug/draft-runtime")
def debug_draft_runtime():
    """Mesmo critério que debug_draft_runtime.py no projeto mãe (n por campeão, DF, paths)."""
    from core.lol.db_converter import find_latest_csv
    from core.lol.draft import LoLDraftAnalyzer
    from core.lol.oracle_team_games import get_draft_oracle_dataframe
    from core.shared.paths import BASE_DIR as paths_base, path_in_data, path_in_models

    csv_path = find_latest_csv()
    csv_size = None
    if csv_path and os.path.isfile(csv_path):
        try:
            csv_size = os.path.getsize(csv_path)
        except OSError:
            csv_size = None

    df = get_draft_oracle_dataframe()
    shape = None
    leagues = None
    if df is not None and not df.empty:
        shape = [int(df.shape[0]), int(df.shape[1])]
        if "league" in df.columns:
            leagues = sorted(str(x) for x in df["league"].dropna().unique())

    champs = [
        "Rumble",
        "Nocturne",
        "Ryze",
        "Kalista",
        "Renata Glasc",
        "Ornn",
        "Pantheon",
        "Anivia",
        "Sivir",
        "Neeko",
    ]
    major = ["LCK", "LPL", "LCS", "CBLOL", "LCP", "LEC"]

    a = LoLDraftAnalyzer()
    load_ok = a.load_models()
    n_games = {}
    if load_ok:
        for c in champs:
            n_games[c] = int(a._count_games_in_oracle(major, c))

    return {
        "BASE_DIR": str(paths_base),
        "DATA_DIR": path_in_data(""),
        "MODELS_DIR": path_in_models(""),
        "find_latest_csv": csv_path,
        "oracle_csv_size": csv_size,
        "df_shape": shape,
        "leagues_in_df": leagues,
        "load_models": load_ok,
        "n_games_major_leagues": n_games,
    }


@app.get("/api/lol/teams")
def lol_teams(q: str = ""):
    from core.lol.prebets_secondary import _get_team_column
    from core.shared.paths import get_lol_db_path
    import sqlite3

    q = (q or "").strip().lower()
    if len(q) < 2:
        return []

    db_path = get_lol_db_path()
    if not db_path or not os.path.exists(db_path):
        return []

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        team_col = _get_team_column(con)
    except Exception:
        con.close()
        return []

    try:
        # GROUP BY LOWER(TRIM(...)): DISTINCT sozinho deixa "Fnatic"/"fnatic"/"Fnatic " como linhas
        # diferentes no SQLite, o que duplica a lista.
        rows = con.execute(
            f"""
            SELECT MIN(TRIM(CAST({team_col} AS TEXT))) AS team_name
            FROM oracle_matches
            WHERE TRIM(CAST({team_col} AS TEXT)) != ''
              AND LOWER(TRIM(CAST({team_col} AS TEXT))) LIKE ?
            GROUP BY LOWER(TRIM(CAST({team_col} AS TEXT)))
            ORDER BY team_name COLLATE NOCASE
            LIMIT 10
            """,
            (f"%{q}%",),
        ).fetchall()
    except Exception:
        rows = []
    finally:
        con.close()

    return [{"name": r["team_name"]} for r in rows if r["team_name"]]


@app.get("/api/lol/players")
def lol_players(q: str = ""):
    from core.shared.paths import get_lol_db_path
    import sqlite3

    q = (q or "").strip().lower()
    if len(q) < 2:
        return []

    db_path = get_lol_db_path()
    if not db_path or not os.path.exists(db_path):
        return []

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(oracle_matches)").fetchall()}
        pcol = "playername" if "playername" in cols else ("player" if "player" in cols else None)
        if not pcol:
            return []
        rows = con.execute(
            f"""
            SELECT MIN(TRIM(CAST({pcol} AS TEXT))) AS player_name
            FROM oracle_matches
            WHERE TRIM(CAST({pcol} AS TEXT)) != ''
              AND LOWER(TRIM(CAST({pcol} AS TEXT))) LIKE ?
            GROUP BY LOWER(TRIM(CAST({pcol} AS TEXT)))
            ORDER BY player_name COLLATE NOCASE
            LIMIT 10
            """,
            (f"%{q}%",),
        ).fetchall()
    except Exception:
        rows = []
    finally:
        con.close()

    return [{"name": r["player_name"]} for r in rows if r["player_name"]]


def update_lol():
    print("Atualizando LoL...")
    # aqui você coloca seu código depois

def update_dota():
    print("Atualizando Dota...")
    # aqui entra seu scraping

scheduler = BackgroundScheduler()
scheduler.add_job(update_lol, "interval", hours=24)
scheduler.add_job(update_dota, "interval", hours=6)
scheduler.start()

@app.get("/", response_class=HTMLResponse)
def home():
    return (BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")


@app.get("/player", response_class=HTMLResponse)
def player_page():
    return (BASE_DIR / "templates" / "player.html").read_text(encoding="utf-8")


@app.get("/lol-players", response_class=HTMLResponse)
def lol_players_page():
    return (BASE_DIR / "templates" / "player.html").read_text(encoding="utf-8")
