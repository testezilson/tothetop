import os
import re
import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
    WebDriverException,
)


def build_chrome_options():
    """Opções de Chrome: headless + flags para Linux/Railway quando SELENIUM_HEADLESS=1 ou RAILWAY."""
    options = webdriver.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    use_headless = bool(os.environ.get("RAILWAY_ENVIRONMENT")) or os.environ.get("SELENIUM_HEADLESS", "1") == "1"
    if use_headless:
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
    return options

# =========================================================
# Debug helpers
# =========================================================
def _dump_debug(driver, match_id: str | None, prefix: str):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    mid = match_id or "unknown"
    os.makedirs("debug", exist_ok=True)

    html_path = os.path.join("debug", f"{prefix}_{mid}_{ts}.html")
    png_path = os.path.join("debug", f"{prefix}_{mid}_{ts}.png")

    try:
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
    except:
        pass

    try:
        driver.save_screenshot(png_path)
    except:
        pass

    return html_path, png_path


def _extract_match_id(url: str) -> str | None:
    m = re.search(r"/matches/(\d+)", url)
    return m.group(1) if m else None


def _base_match_url(url: str) -> str:
    m = re.search(r"(https?://[^/]+/en/matches/\d+)", url)
    if m:
        return m.group(1).rstrip("/") + "/"
    return url.rstrip("/") + "/"


def _get_main_text(driver) -> str:
    try:
        return driver.execute_script(
            """
            const main = document.querySelector('main') || document.body;
            return main ? (main.innerText || '') : '';
            """
        ) or ""
    except:
        return ""


def _accept_cookies_if_any(driver):
    candidates = [
        "//*[contains(translate(., 'accept', 'ACCEPT'), 'ACCEPT')]",
        "//*[contains(translate(., 'agree', 'AGREE'), 'AGREE')]",
        "//*[contains(translate(., 'got it', 'GOT IT'), 'GOT IT')]",
    ]
    for xp in candidates:
        try:
            els = driver.find_elements(By.XPATH, xp)
            if els:
                driver.execute_script("arguments[0].click();", els[0])
                time.sleep(0.3)
                return
        except:
            pass


def _click_summary_tab_if_present(driver):
    """
    Clica no tab SUMMARY (SPA). Não usar /summary/ direto.
    """
    try:
        els = driver.find_elements(
            By.XPATH,
            "//*[self::a or self::button or self::div]"
            "[contains(translate(normalize-space(.), 'summary', 'SUMMARY'), 'SUMMARY')]"
        )
        for el in els[:12]:
            try:
                if el.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                    time.sleep(0.15)
                    driver.execute_script("arguments[0].click();", el)
                    time.sleep(0.9)
                    return True
            except StaleElementReferenceException:
                continue
            except:
                continue
    except:
        pass
    return False


# =========================================================
# Extractors
# =========================================================
def _extract_teams_from_main(driver):
    """
    Extrai 2 times dentro do <main>, ignorando navbar ("Teams").
    """
    try:
        names = driver.execute_script(
            r"""
            const main = document.querySelector('main');
            if (!main) return [];
            const anchors = Array.from(main.querySelectorAll('a[href*="/teams/"], a[href*="/en/teams/"]'));
            const out = [];
            const seen = new Set();
            for (const a of anchors) {
              const t = (a.innerText || '').trim();
              if (!t) continue;

              const low = t.toLowerCase();
              if (low === 'teams') continue;
              if (t.length < 2) continue;

              if (seen.has(low)) continue;
              seen.add(low);
              out.push(t);
              if (out.length >= 2) break;
            }
            return out;
            """
        )
        if isinstance(names, list) and len(names) >= 2:
            return str(names[0]).strip(), str(names[1]).strip()
    except:
        pass
    return None, None


def _extract_series_score(text: str):
    """
    Placar de série: pequeno (<=5-<=5)
    """
    pairs = re.findall(r"\b(\d{1,2})\s*-\s*(\d{1,2})\b", text)
    for a, b in pairs:
        ia, ib = int(a), int(b)
        if ia <= 5 and ib <= 5:
            return ia, ib
    return None, None


def _extract_date_best_effort(driver, text: str):
    try:
        time_el = driver.find_elements(By.CSS_SELECTOR, "time[datetime]")
        if time_el:
            iso = time_el[0].get_attribute("datetime")
            if iso:
                dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                return dt.astimezone().strftime("%d.%m.%y at %H:%M")
    except:
        pass

    m = re.search(r"\b\d{2}\.\d{2}\.\d{2}\s+at\s+\d{2}:\d{2}\b", text)
    if m:
        return m.group(0)

    m = re.search(r"\b(?:Today|Yesterday|Tomorrow)\s+at\s+\d{1,2}:\d{2}\b", text, re.IGNORECASE)
    if m:
        s = m.group(0)
        return s[0].upper() + s[1:]
    return None


def _extract_duration_mmss(text: str):
    """
    Duração MM:SS (39:24, 42:04...). Ignora 'Today at 14:00'.
    """
    hits = []
    for m in re.finditer(r"(\d{1,3}:\d{2})", text):
        val = m.group(1)
        start = m.start(1)
        prefix = text[max(0, start - 6):start].lower()
        if "at " in prefix:
            continue
        hits.append(val)
    return hits[-1] if hits else None


# =========================================================
# MAP extraction (click MAP i + pick closest visible score)
# =========================================================
def _click_map_tab(driver, map_i: int) -> bool:
    """
    Tenta clicar em "MAP i". (tab/botão/accordion)
    Melhorado: aguarda melhor após clicar para garantir renderização
    """
    xpath = (
        "//*[self::a or self::button or self::div or self::span]"
        f"[contains(translate(normalize-space(.), 'map', 'MAP'), 'MAP {map_i}')]"
    )
    els = driver.find_elements(By.XPATH, xpath)
    for el in els[:12]:
        try:
            if el.is_displayed():
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                time.sleep(0.2)
                driver.execute_script("arguments[0].click();", el)
                # Aguarda mais tempo após clicar para garantir renderização do conteúdo
                time.sleep(0.9)
                return True
        except StaleElementReferenceException:
            continue
        except:
            continue
    return False


def _get_scores_ranked_by_closeness_to_map(driver, map_i: int):
    """
    Retorna lista de placares "NN-NN" visíveis, ordenados por proximidade ao rótulo "MAP i".
    Melhorado: remove duplicatas no próprio JavaScript e filtra melhor o contexto do MAP.
    """
    try:
        ranked = driver.execute_script(
            r"""
            const mapI = arguments[0];
            const root = document.querySelector('main') || document.body;
            if (!root) return [];

            // acha o nó do "MAP i"
            const xp = `//*[contains(translate(normalize-space(.), 'map', 'MAP'), 'MAP ${mapI}')]`;
            const snap = document.evaluate(xp, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
            if (snap.snapshotLength === 0) return [];

            const mapNode = snap.snapshotItem(0);
            const mr = mapNode.getBoundingClientRect();
            const mapTop = mr.top;
            const mapLeft = mr.left;

            // Tenta encontrar o container pai do MAP (panel/tab content)
            let mapContainer = mapNode;
            for (let i = 0; i < 5; i++) {
                mapContainer = mapContainer.parentElement;
                if (!mapContainer) break;
                const containerRect = mapContainer.getBoundingClientRect();
                const containerStyle = window.getComputedStyle(mapContainer);
                // Se encontrou um container visível e grande, usa ele
                if (containerRect.width > 200 && containerRect.height > 100 && 
                    containerStyle.display !== 'none' && containerStyle.visibility !== 'hidden') {
                    break;
                }
            }

            const out = [];
            const seenScores = new Set(); // Deduplicação no JavaScript
            const nodes = root.querySelectorAll('*');

            for (const el of nodes) {
              const r = el.getBoundingClientRect();
              if (!r || r.width <= 0 || r.height <= 0) continue;

              const st = window.getComputedStyle(el);
              if (!st || st.visibility === 'hidden' || st.display === 'none' || parseFloat(st.opacity || '1') === 0) continue;

              const t = (el.innerText || '').trim();
              if (!t) continue;

              const m = t.match(/^(\d{1,3})\s*-\s*(\d{1,3})$/);
              if (!m) continue;

              const a = parseInt(m[1],10), b = parseInt(m[2],10);
              if (a < 0 || b < 0 || a > 250 || b > 250) continue;
              if (a <= 5 && b <= 5) continue; // remove 2-0

              const score = `${a}-${b}`;
              if (seenScores.has(score)) continue; // Pula se já viu esse score
              seenScores.add(score);

              // Prioriza scores que estão dentro ou próximos do container do MAP
              const isInContainer = mapContainer && mapContainer.contains(el);
              const dy = Math.abs(r.top - mapTop);
              const dx = Math.abs(r.left - mapLeft);
              // Penaliza mais se está longe, mas bonus se está no container
              const cost = dy + dx * 0.2 - (isInContainer ? 500 : 0);

              out.push({score: score, cost, element: el, inContainer: isInContainer});
            }

            // Ordena: primeiro os que estão no container, depois por proximidade
            out.sort((x, y) => {
                if (x.inContainer !== y.inContainer) return y.inContainer - x.inContainer;
                return x.cost - y.cost;
            });
            
            return out.map(o => o.score);
            """,
            map_i
        )
        if isinstance(ranked, list):
            # Remove duplicatas mantendo ordem (redundante mas garante)
            seen = set()
            uniq = []
            for s in ranked:
                s = str(s).strip()
                if not s:
                    continue
                if s in seen:
                    continue
                seen.add(s)
                uniq.append(s)
            return uniq
    except:
        pass
    return []


def _extract_map_kills_by_clicking(driver, maps_played: int | None, max_maps: int = 5):
    """
    Estratégia final:
      - clica MAP1, MAP2...
      - para cada MAP i: pega o score visível MAIS PRÓXIMO do rótulo MAP i
      - não reutiliza o mesmo score em mapas diferentes
    Melhorado: melhor filtro de duplicatas e espera mais tempo para renderizar
    """
    target = maps_played if maps_played and maps_played > 0 else 1
    target = min(target, max_maps)

    used = set()
    out = []

    for i in range(1, target + 1):
        # Clica no MAP tab
        clicked = _click_map_tab(driver, i)
        if not clicked:
            # Se não conseguiu clicar no MAP i, tenta continuar
            continue

        # Espera mais tempo para garantir que o conteúdo foi renderizado
        time.sleep(0.8)

        # Scroll para garantir que o conteúdo está visível
        driver.execute_script("window.scrollBy(0, 300);")
        time.sleep(0.4)
        driver.execute_script("window.scrollBy(0, -200);")
        time.sleep(0.4)

        ranked = _get_scores_ranked_by_closeness_to_map(driver, i)
        if not ranked:
            # Se não encontrou scores para este MAP, para
            break

        # Procura o primeiro score que ainda não foi usado
        pick = None
        for s in ranked:
            if s not in used:
                pick = s
                break

        if not pick:
            # Se todos os scores já foram usados, isso indica problema
            # Não adiciona nada e para
            break

        # Marca como usado e adiciona à lista
        used.add(pick)
        out.append(pick)

    return out


def _extract_map_kills_fallback_global(driver, maps_played: int | None):
    """
    Fallback: pega scores visíveis no main (sem MAP) e retorna os primeiros N.
    """
    target = maps_played if maps_played and maps_played > 0 else 1
    try:
        scores = driver.execute_script(
            r"""
            const root = document.querySelector('main') || document.body;
            if (!root) return [];
            const out = [];
            const nodes = root.querySelectorAll('*');
            for (const el of nodes) {
              const r = el.getBoundingClientRect();
              if (!r || r.width <= 0 || r.height <= 0) continue;

              const st = window.getComputedStyle(el);
              if (!st || st.visibility === 'hidden' || st.display === 'none') continue;

              const t = (el.innerText || '').trim();
              if (!t) continue;

              const m = t.match(/^(\d{1,3})\s*-\s*(\d{1,3})$/);
              if (!m) continue;

              const a = parseInt(m[1],10), b = parseInt(m[2],10);
              if (a < 0 || b < 0 || a > 250 || b > 250) continue;
              if (a <= 5 && b <= 5) continue;

              out.push(`${a}-${b}`);
            }
            return out;
            """
        )
        if isinstance(scores, list) and scores:
            cleaned = []
            seen = set()
            for s in scores:
                s = str(s).strip()
                if not s:
                    continue
                if s in seen:
                    continue
                seen.add(s)
                cleaned.append(s)
            return cleaned[:target] if len(cleaned) >= target else cleaned
    except:
        pass
    return []


# =========================================================
# Main
# =========================================================
def scrap_match_page(url: str):
    driver = webdriver.Chrome(options=build_chrome_options())
    wait = WebDriverWait(driver, 20)

    base_url = _base_match_url(url)
    match_id = _extract_match_id(base_url)

    data = {
        "team_radiant": None,
        "team_dire": None,
        "score_radiant": None,
        "score_dire": None,
        "duration": None,
        "kills_radiant": None,
        "kills_dire": None,
        "kills_total": None,
        "map_kills": [],
        "map_kills_text": None,
        "date": None,
    }

    try:
        print(f"🌐 Abrindo: {base_url}")
        driver.get(base_url)

        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(1.0)

        _accept_cookies_if_any(driver)

        last_err = None

        for attempt in range(1, 5):
            try:
                # ajuda renderizar tabs e summary
                driver.execute_script("window.scrollBy(0, 1000);")
                time.sleep(0.6)

                _click_summary_tab_if_present(driver)

                wait.until(lambda d: (d.execute_script("return !!document.querySelector('main')") is True))
                time.sleep(0.6)

                text = _get_main_text(driver)

                # teams
                t1, t2 = _extract_teams_from_main(driver)
                data["team_radiant"] = t1.upper() if t1 else None
                data["team_dire"] = t2.upper() if t2 else None

                # score série
                sr, sd = _extract_series_score(text)
                data["score_radiant"], data["score_dire"] = sr, sd

                maps_played = None
                if sr is not None and sd is not None:
                    maps_played = sr + sd

                # date/duration
                data["date"] = _extract_date_best_effort(driver, text)
                data["duration"] = _extract_duration_mmss(text)

                # força lazy render (MAP2 às vezes só aparece após scroll)
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(0.8)
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(0.3)

                # MAP KILLS: clique + score mais próximo do MAP i
                map_kills = _extract_map_kills_by_clicking(driver, maps_played, max_maps=5)

                # fallback
                if not map_kills:
                    map_kills = _extract_map_kills_fallback_global(driver, maps_played)

                # corta se necessário
                if maps_played and maps_played > 0 and len(map_kills) > maps_played:
                    map_kills = map_kills[:maps_played]

                data["map_kills"] = map_kills
                data["map_kills_text"] = " | ".join(map_kills) if map_kills else None

                # soma kills (compatibilidade EV)
                if map_kills:
                    k1_sum = 0
                    k2_sum = 0
                    for s in map_kills:
                        a, b = s.split("-")
                        k1_sum += int(a)
                        k2_sum += int(b)
                    data["kills_radiant"] = k1_sum
                    data["kills_dire"] = k2_sum
                    data["kills_total"] = k1_sum + k2_sum

                if data["team_radiant"] and data["team_dire"] and data["map_kills"]:
                    print("   ✅ Extração OK:", {k: data[k] for k in data if k != "map_kills"})
                    return data

                last_err = RuntimeError(f"Dados incompletos (tentativa {attempt}/4)")
                time.sleep(0.9)

            except (StaleElementReferenceException, TimeoutException, WebDriverException) as e:
                last_err = e
                time.sleep(1.0)
                continue

        html_path, png_path = _dump_debug(driver, match_id=match_id, prefix="cyberscore_match_fail")
        print(f"   ❌ Falhou ao extrair dados após retries: {type(last_err).__name__ if last_err else 'Unknown'}")
        print(f"   🧾 Dump salvo em {html_path} e {png_path}")
        return data

    except Exception as e:
        html_path, png_path = _dump_debug(driver, match_id=match_id, prefix="cyberscore_match_exception")
        print(f"   ❌ EXCEÇÃO: {type(e).__name__}: {e}")
        print(f"   🧾 Dump salvo em {html_path} e {png_path}")
        return data

    finally:
        try:
            driver.quit()
        except:
            pass
