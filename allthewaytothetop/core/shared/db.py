"""
Gerenciamento de banco de dados SQLite para histórico de apostas.
"""
import sqlite3
import os
from datetime import datetime
from core.shared.paths import path_in_user_data


def get_bets_db():
    """
    Retorna o caminho do banco de dados de apostas.
    """
    return path_in_user_data('bets.db')


def init_bets_db():
    """
    Inicializa o banco de dados de apostas se não existir.
    """
    db_path = get_bets_db()
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game TEXT NOT NULL,
            league TEXT,
            market TEXT NOT NULL,
            line REAL,
            odd REAL,
            probability REAL,
            ev REAL,
            choice TEXT,
            timestamp TEXT NOT NULL,
            notes TEXT
        )
    ''')
    
    conn.commit()
    conn.close()


def save_bet(game, league, market, line, odd, probability, ev, choice, notes=None):
    """
    Salva uma aposta no histórico.
    
    Args:
        game: "LoL" ou "Dota"
        league: Nome da liga (ex: "LCK", "LPL")
        market: Tipo de mercado (ex: "Total Kills", "Map Winner")
        line: Linha da aposta (ex: 24.5)
        odd: Odd da casa de apostas
        probability: Probabilidade calculada (0-1)
        ev: Expected Value (EV)
        choice: "UNDER", "OVER", "Team1", "Team2", etc.
        notes: Notas adicionais (opcional)
    """
    init_bets_db()
    
    db_path = get_bets_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO bets (game, league, market, line, odd, probability, ev, choice, timestamp, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (game, league, market, line, odd, probability, ev, choice, datetime.now().isoformat(), notes))
    
    conn.commit()
    conn.close()


def get_bet_history(limit=100):
    """
    Retorna o histórico de apostas.
    
    Args:
        limit: Número máximo de apostas a retornar
    
    Returns:
        Lista de dicionários com as apostas
    """
    init_bets_db()
    
    db_path = get_bets_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, game, league, market, line, odd, probability, ev, choice, timestamp, notes
        FROM bets
        ORDER BY timestamp DESC
        LIMIT ?
    ''', (limit,))
    
    columns = [desc[0] for desc in cursor.description]
    bets = [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    conn.close()
    return bets


def export_bets_to_csv(output_path):
    """
    Exporta o histórico de apostas para CSV.
    
    Args:
        output_path: Caminho do arquivo CSV de saída
    """
    import pandas as pd
    
    bets = get_bet_history(limit=10000)  # Exportar tudo
    
    if not bets:
        return False
    
    df = pd.DataFrame(bets)
    df.to_csv(output_path, index=False)
    return True
