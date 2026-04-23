"""
Funções utilitárias compartilhadas.
"""
import pandas as pd


def format_percentage(value, decimals=2):
    """Formata um valor como porcentagem."""
    return f"{value * 100:.{decimals}f}%"


def format_ev(ev):
    """Formata o Expected Value."""
    if ev is None:
        return "N/A"
    return f"{ev:.2f}%"


def get_confidence_label(probability, threshold=0.5):
    """
    Retorna o label de confiança baseado na probabilidade.
    
    Args:
        probability: Probabilidade (0-1)
        threshold: Threshold de referência (geralmente 0.5)
    
    Returns:
        "High", "Medium" ou "Low"
    """
    diff = abs(probability - threshold)
    if diff >= 0.20:
        return "High"
    elif diff >= 0.10:
        return "Medium"
    else:
        return "Low"


# Ligas Major do LoL
MAJOR_LEAGUES = {"LPL", "LCK", "LEC", "CBLOL", "LCS", "LCP"}


def is_major_league(league):
    """Verifica se uma liga é Major."""
    return league in MAJOR_LEAGUES
