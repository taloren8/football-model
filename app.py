import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET

st.set_page_config(
    page_title="⚽ מנתח משחקי כדורגל",
    page_icon="⚽",
    layout="wide"
)

# RTL
st.markdown("""
<style>
    .stApp { direction: rtl; }
    .stSelectbox { direction: rtl; }
    h1, h2, h3, p { text-align: right; }
</style>
""", unsafe_allow_html=True)

# ============================================
# הגדרות
# ============================================
API_KEY = st.secrets["API_KEY"]
RAPIDAPI_KEY = st.secrets["RAPIDAPI_KEY"]
HEADERS = {"x-apisports-key": API_KEY}
SEASON = 2025

LEAGUES = {
    "Premier League": 39,
    "La Liga": 140,
    "Bundesliga": 78,
    "Serie A": 135,
    "Ligue 1": 61,
    "Eredivisie": 88,
    "Ligat Ha'al": 383
}

ערים = {
    "Premier League": "London",
    "La Liga": "Madrid",
    "Bundesliga": "Munich",
    "Serie A": "Milan",
    "Ligue 1": "Paris",
    "Eredivisie": "Amsterdam",
    "Ligat Ha'al": "Tel Aviv"
}

היום = datetime.now().strftime("%Y-%m-%d")
לפני_חודשיים = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")

# ============================================
# פונקציות
# ============================================
@st.cache_data(ttl=3600)
def טען_נתונים():
    all_matches = []
    for league_name, league_id in LEAGUES.items():
        url = "https://v3.football.api-sports.io/fixtures"
        params = {"league": league_id, "season": SEASON,
                  "from": לפני_חודשיים, "to": היום, "status": "FT"}
        response = requests.get(url, headers=HEADERS, params=params)
        data = response.json()
        if data.get("errors"): continue
        for match in data["response"]:
            all_matches.append({
                "ליגה": league_name,
                "תאריך": match["fixture"]["date"][:10],
                "בית": match["teams"]["home"]["name"],
                "חוץ": match["teams"]["away"]["name"],
                "שערי בית": match["goals"]["home"],
                "שערי חוץ": match["goals"]["away"],
                "תוצאה": "בית" if match["teams"]["home"]["winner"] else
                          "חוץ" if match["teams"]["away"]["winner"] else "תיקו"
            })
    return pd.DataFrame(all_matches)

@st.cache_data(ttl=3600)
def קבל_מצב_טבלה(league_id):
    url = "https://v3.football.api-sports.io/standings"
    params = {"league": league_id, "season": SEASON}
    response = requests.get(url, headers=HEADERS, params=params)
    data = response.json()
    if not data["response"]: return {}
    טבלה = {}
    standings = data["response"][0]["league"]["standings"][0]
    סה_כ = len(standings)
    for קבוצה in standings:
        שם = קבוצה["team"]["name"]
        מקום = קבוצה["rank"]
        נקודות = קבוצה["points"]
        אחוז = מקום / סה_כ
        if מקום <= 3: אזור, בונוס = "מירוץ אליפות 🏆", 5
        elif מקום <= 6: אזור, בונוס = "אזור אירופה 🌍", 6
        elif אחוז >= 0.85: אזור, בונוס = "אזור הורדה 🔴", 10
        elif אחוז >= 0.75: אזור, בונוס = "אזור פלייאוף ⚠️", 8
        else: אזור, בונוס = "אמצע טבלה ➖", -5
        טבלה[שם] = {"מקום": מקום, "נקודות": נקודות, "אזור": אזור, "בונוס": בונוס}
    return טבלה

def חשב_ציון_טבלה(קבוצה, ליגה, טבלאות):
    if ליגה not in טבלאות or קבוצה not in טבלאות[ליגה]: return 0, "לא ידוע"
    נ = טבלאות[ליגה][קבוצה]
    return נ["בונוס"], f"מקום {נ['מקום']} | {נ['נקודות']} נק' | {נ['אזור']}"

def חשב_מומנטום(קבוצה, df, num_matches=5):
    df_ליגה = df[df["ליגה"].isin(list(LEAGUES.keys()))].copy()
    בית = df_ליגה[df_ליגה["בית"] == קבוצה].copy()
    בית["תוצאה_קבוצה"] = בית["תוצאה"].map({"בית":"ניצחון","תיקו":"תיקו","חוץ":"הפסד"})
    חוץ = df_ליגה[df_ליגה["חוץ"] == קבוצה].copy()
    חוץ["תוצאה_קבוצה"] = חוץ["תוצאה"].map({"חוץ":"ניצחון","תיקו":"תיקו","בית":"הפסד"})
    כל_משחקים = pd.concat([בית[["תאריך","תוצאה_קבוצה"]],
                             חוץ[["תאריך","תוצאה_קבוצה"]]]).sort_values("תאריך").tail(num_matches)
    if len(כל_משחקים) < 3:
        בית2 = df[df["בית"] == קבוצה].copy()
        בית2["תוצאה_קבוצה"] = בית2["תוצאה"].map({"בית":"ניצחון","תיקו":"תיקו","חוץ":"הפסד"})
        חוץ2 = df[df["חוץ"] == קבוצה].copy()
        חוץ2["תוצאה_קבוצה"] = חוץ2["תוצאה"].map({"חוץ":"ניצחון","תיקו":"תיקו","בית":"הפסד"})
        כל_משחקים = pd.concat([בית2[["תאריך","תוצאה_קבוצה"]],
                                 חוץ2[["תאריך","תוצאה_קבוצה"]]]).sort_values("תאריך").tail(num_matches)
    משקולות = list(range(1, len(כל_משחקים) + 1))
    נקודות_משוקללות = משקל_מקסימום = 0
    תוצאות_רשימה = []
    for i, (_, שורה) in enumerate(כל_משחקים.iterrows()):
        משקל = משקולות[i]
        תוצאה = שורה["תוצאה_קבוצה"]
        תוצאות_רשימה.append(תוצאה)
        if תוצאה == "ניצחון": נקודות_משוקללות += 3 * משקל
        elif תוצאה == "תיקו": נקודות_משוקללות += 1 * משקל
        משקל_מקסימום += 3 * משקל
    רצף = 0
    for תוצאה in reversed(תוצאות_רשימה):
        if תוצאה == "ניצחון": רצף += 1
        else: break
    בונוס = 10 if רצף >= 3 else 5 if רצף == 2 else 0
    אחוז = round((נקודות_משוקללות / משקל_מקסימום) * 100) if משקל_מקסימום > 0 else 0
    return {"מומנטום": min(92, אחוז + בונוס), "משחקים": תוצאות_רשימה, "רצף_ניצחונות": רצף}

def קבל_h2h(id_בית, id_חוץ):
    if not id_בית or not id_חוץ: return None
    url = "https://v3.football.api-sports.io/fixtures/headtohead"
    params = {"h2h": f"{id_בית}-{id_חוץ}", "from": "2020-01-01", "to": היום}
    response = requests.get(url, headers=HEADERS, params=params)
    data = response.json()
    if not data["response"]: return None
    ניצחונות_בית = ניצחונות_חוץ = תיקו = 0
    שערים = []
    משחקים = sorted(data["response"], key=lambda x: x["fixture"]["date"])[-10:]
    for משחק in משחקים:
        בית_id = משחק["teams"]["home"]["id"]
        תב = משחק["teams"]["home"]["winner"]
        תח = משחק["teams"]["away"]["winner"]
        שערי_בית = משחק["goals"]["home"] or 0
        שערי_חוץ = משחק["goals"]["away"] or 0
        שערים.append(שערי_בית + שערי_חוץ)
        if בית_id == id_בית:
            if תב: ניצחונות_בית += 1
            elif תח: ניצחונות_חוץ += 1
            else: תיקו += 1
        else:
            if תח: ניצחונות_בית += 1
            elif תב: ניצחונות_חוץ += 1
            else: תיקו += 1
    return {"מספר_משחקים": len(משחקים), "ניצחונות_בית": ניצחונות_בית,
            "ניצחונות_חוץ": ניצחונות_חוץ, "תיקו": תיקו,
            "ממוצע_שערים": round(sum(שערים)/len(שערים), 2) if שערים else 2.0}

def חשב_טווח_שערים(קבוצת_בית, קבוצת_חוץ, df):
    משחקי_בית = df[df["בית"] == קבוצת_בית]
    משחקי_חוץ = df[df["חוץ"] == קבוצת_חוץ]
    if len(משחקי_בית) == 0 or len(משחקי_חוץ) == 0: return None, None, None
    סה_כ = ((משחקי_בית["שערי בית"].mean() + משחקי_חוץ["שערי בית"].mean()) / 2 +
             (משחקי_חוץ["שערי חוץ"].mean() + משחקי_בית["שערי חוץ"].mean()) / 2)
    def התפלגות(משחקים):
        ס = משחקים["שערי בית"] + משחקים["שערי חוץ"]
        n = len(ס)
        if n == 0: return {"0-1": 33, "2-3": 34, "4+": 33}
        return {"0-1": round((ס<=1).sum()/n*100),
                "2-3": round(((ס>=2)&(ס<=3)).sum()/n*100),
                "4+": round((ס>=4).sum()/n*100)}
    ה_בית = התפלגות(משחקי_בית)
    ה_חוץ = התפלגות(משחקי_חוץ)
    ה_משוקללת = {ט: round((ה_בית[ט]+ה_חוץ[ט])/2) for ט in ["0-1","2-3","4+"]}
    טווח_מספרי = "0-1" if סה_כ<=1.5 else "2-3" if סה_כ<=3.5 else "4+"
    ציונים = {ט: ה_משוקללת[ט] + (20 if ט==טווח_מספרי else 0) for ט in ["0-1","2-3","4+"]}
    return max(ציונים, key=ציונים.get), round(סה_כ, 2), ה_משוקללת

@st.cache_data(ttl=1800)
def קבל_קרנות(team_id, league_id, num_matches=5):
    url = "https://v3.football.api-sports.io/fixtures"
    params = {"team": team_id, "league": league_id, "season": SEASON, "last": num_matches, "status": "FT"}
    response = requests.get(url, headers=HEADERS, params=params)
    data = response.json()
    if data.get("errors") or not data["response"]: return None
    קרנות_לטובת = []
    for משחק in data["response"][:num_matches]:
        fixture_id = משחק["fixture"]["id"]
        url_סטט = "https://v3.football.api-sports.io/fixtures/statistics"
        response_סטט = requests.get(url_סטט, headers=HEADERS, params={"fixture": fixture_id})
        data_סטט = response_סטט.json()
        if not data_סטט["response"]: continue
        for קבוצה_סטט in data_סטט["response"]:
            if קבוצה_סטט["team"]["id"] == team_id:
                for סטטיסטיקה in קבוצה_סטט["statistics"]:
                    if סטטיסטיקה["type"] == "Corner Kicks":
                        קרנות_לטובת.append(int(סטטיסטיקה["value"] or 0))
    return round(sum(קרנות_לטובת)/len(קרנות_לטובת), 1) if קרנות_לטובת else None

@st.cache_data(ttl=3600)
def קבל_פציעות(team_id, league_id):
    url = "https://v3.football.api-sports.io/injuries"
    params = {"team": team_id, "league": league_id, "season": SEASON}
    response = requests.get(url, headers=HEADERS, params=params)
    data = response.json()
    if data.get("errors") or not data["response"]: return []
    ממוינים = sorted(data["response"], key=lambda x: x["fixture"]["date"], reverse=True)
    תאריך_אחרון = ממוינים[0]["fixture"]["date"][:10]
    שחקנים_שראינו = set()
    נעדרים = []
    for רשומה in ממוינים:
        if רשומה["fixture"]["date"][:10] != תאריך_אחרון: break
        if רשומה["team"]["id"] != team_id: continue
        player_id = רשומה["player"]["id"]
        if player_id in שחקנים_שראינו: continue
        שחקנים_שראינו.add(player_id)
        נעדרים.append({"שם": רשומה["player"]["name"], "סיבה": רשומה["player"]["reason"]})
    return נעדרים

@st.cache_data(ttl=600)
def קבל_חדשות(שם_קבוצה):
    try:
        url = f"https://news.google.com/rss/search?q={שם_קבוצה}+football&hl=en&gl=US&ceid=US:en"
        response = requests.get(url, timeout=5)
        root = ET.fromstring(response.content)
        חדשות = []
        for item in root.findall(".//item")[:3]:
            כותרת = item.find("title").text
            חדשות.append(כותרת)
        return חדשות
    except: return []

def קבל_דעה_שנייה(קבוצת_בית, קבוצת_חוץ):
    url = "https://football-prediction-api.p.rapidapi.com/api/v2/predictions"
    params = {"market": "classic", "iso_date": היום, "federation": "UEFA"}
    headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": "football-prediction-api.p.rapidapi.com"}
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    if isinstance(data, dict) and data.get("error"): return None
    תחזיות = data if isinstance(data, list) else data.get("data", [])
    def נרמל(שם): return שם.lower().strip()
    בית_נ = נרמל(קבוצת_בית)
    חוץ_נ = נרמל(קבוצת_חוץ)
    for ת in תחזיות:
        home_api = נרמל(ת.get("home_team", ""))
        away_api = נרמל(ת.get("away_team", ""))
        בית_נמצא = בית_נ in home_api or home_api in בית_נ or any(מ in home_api for מ in בית_נ.split() if len(מ) > 3)
        חוץ_נמצא = חוץ_נ in away_api or away_api in חוץ_נ or any(מ in away_api for מ in חוץ_נ.split() if len(מ) > 3)
        if בית_נמצא and חוץ_נמצא:
            pred = ת.get("prediction", "")
            if pred == "1": pred_טקסט = f"ניצחון {ת['home_team']}"
            elif pred == "2": pred_טקסט = f"ניצחון {ת['away_team']}"
            elif pred == "X": pred_טקסט = "תיקו"
            else: pred_טקסט = "לא ידוע"
            odds = ת.get("odds", {})
            return {"תחזית": pred_טקסט, "תחזית_מספר": pred,
                    "מכרז_בית": odds.get("1","N/A"), "מכרז_תיקו": odds.get("X","N/A"),
                    "מכרז_חוץ": odds.get("2","N/A")}
    return None

def זהה_משבר(קבוצה, df):
    df_ליגה = df[df["ליגה"].isin(list(LEAGUES.keys()))].copy()
    בית = df_ליגה[df_ליגה["בית"] == קבוצה].copy()
    בית["תוצאה_קבוצה"] = בית["תוצאה"].map({"בית":"ניצחון","תיקו":"תיקו","חוץ":"הפסד"})
    חוץ = df_ליגה[df_ליגה["חוץ"] == קבוצה].copy()
    חוץ["תוצאה_קבוצה"] = חוץ["תוצאה"].map({"חוץ":"ניצחון","תיקו":"תיקו","בית":"הפסד"})
    כל_משחקים = pd.concat([בית[["תאריך","תוצאה_קבוצה"]], חוץ[["תאריך","תוצאה_קבוצה"]]]).sort_values("תאריך").tail(6)
    if len(כל_משחקים) < 4: return False, ""
    אחרונים_4 = כל_משחקים.tail(4)["תוצאה_קבוצה"].tolist()
    if אחרונים_4.count("הפסד") >= 3:
        return True, f"⚠️ משבר! {אחרונים_4.count('הפסד')} הפסדות מתוך 4 אחרונים"
    ראשונים_2 = כל_משחקים.head(2)["תוצאה_קבוצה"].tolist()
    אחרונים_2 = כל_משחקים.tail(2)["תוצאה_קבוצה"].tolist()
    if ראשונים_2.count("ניצחון") == 2 and אחרונים_2.count("הפסד") == 2:
        return True, "⚠️ ירידה חדה — בדוק שינויים בקבוצה"
    return False, ""

# ============================================
# ממשק Streamlit
# ============================================
st.title("⚽ מנתח משחקי כדורגל")
st.markdown(f"*נתונים עדכניים — {לפני_חודשיים} עד {היום}*")

# טעינת נתונים
with st.spinner("טוען נתונים..."):
    df = טען_נתונים()
    טבלאות = {ל: קבל_מצב_טבלה(league_id) for ל, league_id in LEAGUES.items()}

קבוצות_לפי_ליגה = {ל: sorted(df[df["ליגה"] == ל]["בית"].unique().tolist()) for ל in LEAGUES.keys()}

קבוצות_ids = {
    "Liverpool": 40, "Arsenal": 42, "Manchester City": 50, "Chelsea": 49,
    "Tottenham": 47, "Manchester United": 33, "Newcastle": 34, "Aston Villa": 66,
    "Brighton": 51, "West Ham": 48, "Wolves": 39, "Crystal Palace": 52,
    "Fulham": 36, "Brentford": 55, "Nottingham Forest": 65, "Everton": 45,
    "Leicester": 46, "Southampton": 41, "Ipswich": 57, "Bournemouth": 35,
    "Real Madrid": 541, "Barcelona": 529, "Atletico Madrid": 530, "Sevilla": 536,
    "Real Betis": 543, "Valencia": 532, "Athletic Club": 531, "Villarreal": 533,
    "Real Sociedad": 548, "Girona": 547, "Osasuna": 727, "Getafe": 546,
    "Rayo Vallecano": 728, "Mallorca": 538, "Las Palmas": 534, "Celta Vigo": 542,
    "Alaves": 720, "Leganes": 723, "Espanyol": 544, "Valladolid": 724,
    "Bayern München": 157, "Borussia Dortmund": 165, "Bayer Leverkusen": 168,
    "RB Leipzig": 173, "Eintracht Frankfurt": 169, "VfB Stuttgart": 172,
    "SC Freiburg": 160, "Werder Bremen": 162, "1899 Hoffenheim": 167,
    "Borussia Mönchengladbach": 163, "Union Berlin": 164, "FC Augsburg": 170,
    "VfL Wolfsburg": 161, "FSV Mainz 05": 178, "Holstein Kiel": 176,
    "FC St. Pauli": 182, "VfL Bochum": 166, "1. FC Heidenheim": 180,
    "Inter": 505, "AC Milan": 489, "Juventus": 496, "Napoli": 492,
    "Atalanta": 499, "Lazio": 487, "AS Roma": 497, "Fiorentina": 502,
    "Bologna": 500, "Torino": 503, "Lecce": 867, "Udinese": 494,
    "Genoa": 508, "Cagliari": 488, "Hellas Verona": 504, "Empoli": 511,
    "Venezia": 517, "Como": 1580, "Parma": 498,
}

# בחירה
col1, col2, col3 = st.columns(3)
with col1:
    ליגה = st.selectbox("ליגה", list(קבוצות_לפי_ליגה.keys()))
with col2:
    קבוצת_בית = st.selectbox("קבוצת בית", קבוצות_לפי_ליגה[ליגה])
with col3:
    אפשרויות_חוץ = [ק for ק in קבוצות_לפי_ליגה[ליגה] if ק != קבוצת_בית]
    קבוצת_חוץ = st.selectbox("קבוצת חוץ", אפשרויות_חוץ)

if st.button("🔍 נתח משחק", type="primary", use_container_width=True):
    id_בית = קבוצות_ids.get(קבוצת_בית)
    id_חוץ = קבוצות_ids.get(קבוצת_חוץ)
    league_id = LEAGUES[ליגה]
    
    with st.spinner("מנתח..."):
        מומנטום_בית = חשב_מומנטום(קבוצת_בית, df)
        מומנטום_חוץ = חשב_מומנטום(קבוצת_חוץ, df)
        בונוס_בית, תיאור_טבלה_בית = חשב_ציון_טבלה(קבוצת_בית, ליגה, טבלאות)
        בונוס_חוץ, תיאור_טבלה_חוץ = חשב_ציון_טבלה(קבוצת_חוץ, ליגה, טבלאות)
        ציון_בית = min(100, מומנטום_בית["מומנטום"] + בונוס_בית + 7)
        ציון_חוץ = min(100, מומנטום_חוץ["מומנטום"] + בונוס_חוץ)
        h2h = קבל_h2h(id_בית, id_חוץ)
        טווח_שערים, סה_כ_צפוי, התפלגות = חשב_טווח_שערים(קבוצת_בית, קבוצת_חוץ, df)
        if h2h and סה_כ_צפוי: סה_כ_צפוי = round((סה_כ_צפוי + h2h["ממוצע_שערים"]) / 2, 2)
        נעדרים_בית = קבל_פציעות(id_בית, league_id) if id_בית else []
        נעדרים_חוץ = קבל_פציעות(id_חוץ, league_id) if id_חוץ else []
        קרנות_בית = קבל_קרנות(id_בית, league_id) if id_בית else None
        קרנות_חוץ = קבל_קרנות(id_חוץ, league_id) if id_חוץ else None
        קרנות_סה_כ = round(קרנות_בית + קרנות_חוץ, 1) if קרנות_בית and קרנות_חוץ else None
        טווח_קרנות = "0-8" if קרנות_סה_כ and קרנות_סה_כ < 9 else "9-11" if קרנות_סה_כ and קרנות_סה_כ < 12 else "12+"
        דעה_שנייה = קבל_דעה_שנייה(קבוצת_בית, קבוצת_חוץ)
        משבר_בית, הודעת_משבר_בית = זהה_משבר(קבוצת_בית, df)
        משבר_חוץ, הודעת_משבר_חוץ = זהה_משבר(קבוצת_חוץ, df)
        חדשות_בית = קבל_חדשות(קבוצת_בית)
        חדשות_חוץ = קבל_חדשות(קבוצת_חוץ)
        
        הפרש = ציון_בית - ציון_חוץ
        נטייה_לתיקו = 0
        if h2h and h2h["תיקו"] >= 3: נטייה_לתיקו += 15
        if (40 < ציון_בית < 70 and 40 < ציון_חוץ < 70): נטייה_לתיקו += 10
        if abs(הפרש) < 8: נטייה_לתיקו += 10
        סף = max(5, 18 - נטייה_לתיקו)
        
        if הפרש > סף:
            המלצה = f"ניצחון {קבוצת_בית}"
            ביטחון = "גבוה 🔥" if הפרש > 25 else "בינוני ⚡"
            צבע = "green"
        elif הפרש < -סף:
            המלצה = f"ניצחון {קבוצת_חוץ}"
            ביטחון = "גבוה 🔥" if הפרש < -25 else "בינוני ⚡"
            צבע = "green"
        else:
            המלצה = "תיקו סביר"
            ביטחון = "בינוני ⚡"
            צבע = "orange"
        
        # בדיקת הסכמה
        הסכמה = False
        if דעה_שנייה:
            pred = דעה_שנייה["תחזית_מספר"]
            if pred == "1" and קבוצת_בית.lower() in המלצה.lower(): הסכמה = True
            elif pred == "2" and קבוצת_חוץ.lower() in המלצה.lower(): הסכמה = True
            elif pred == "X" and "תיקו" in המלצה: הסכמה = True
        if הסכמה and "גבוה" in ביטחון: ביטחון = "גבוה מאוד 🔥🔥"

    # תצוגה
    st.markdown("---")
    st.subheader(f"🏟️ {קבוצת_בית} נגד {קבוצת_חוץ} | {ליגה}")
    
    col_בית, col_חוץ = st.columns(2)
    
    with col_בית:
        st.markdown(f"### 📈 {קבוצת_בית}")
        st.metric("ציון סופי", f"{ציון_בית}%", f"מומנטום {מומנטום_בית['מומנטום']}%")
        st.caption(תיאור_טבלה_בית)
        st.caption(f"רצף: {מומנטום_בית['רצף_ניצחונות']} ניצחונות | {מומנטום_בית['משחקים']}")
        if משבר_בית:
            st.error(הודעת_משבר_בית)
        if נעדרים_בית:
            with st.expander(f"🏥 פציעות ({len(נעדרים_בית)})"):
                for נ in נעדרים_בית:
                    st.write(f"❌ {נ['שם']} | {נ['סיבה']}")
        if חדשות_בית:
            with st.expander("📰 חדשות"):
                for ח in חדשות_בית:
                    st.write(f"• {ח[:100]}")
    
    with col_חוץ:
        st.markdown(f"### 📉 {קבוצת_חוץ}")
        st.metric("ציון סופי", f"{ציון_חוץ}%", f"מומנטום {מומנטום_חוץ['מומנטום']}%")
        st.caption(תיאור_טבלה_חוץ)
        st.caption(f"רצף: {מומנטום_חוץ['רצף_ניצחונות']} ניצחונות | {מומנטום_חוץ['משחקים']}")
        if משבר_חוץ:
            st.error(הודעת_משבר_חוץ)
        if נעדרים_חוץ:
            with st.expander(f"🏥 פציעות ({len(נעדרים_חוץ)})"):
                for נ in נעדרים_חוץ:
                    st.write(f"❌ {נ['שם']} | {נ['סיבה']}")
        if חדשות_חוץ:
            with st.expander("📰 חדשות"):
                for ח in חדשות_חוץ:
                    st.write(f"• {ח[:100]}")
    
    st.markdown("---")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if h2h:
            st.info(f"🔄 H2H: {h2h['ניצחונות_בית']}W / {h2h['תיקו']}D / {h2h['ניצחונות_חוץ']}L | ממוצע {h2h['ממוצע_שערים']} שערים")
    with col2:
        if סה_כ_צפוי:
            st.info(f"⚽ שערים: {סה_כ_צפוי} → {טווח_שערים} | {'Over 2.5' if סה_כ_צפוי > 2.5 else 'Under 2.5'}")
            if התפלגות:
                st.caption(f"0-1: {התפלגות['0-1']}% | 2-3: {התפלגות['2-3']}% | 4+: {התפלגות['4+']}%")
    with col3:
        if קרנות_סה_כ:
            st.info(f"🚩 קרנות: {קרנות_סה_כ} → {טווח_קרנות}")
    
    if דעה_שנייה:
        if הסכמה:
            st.success(f"🔮 דעה שנייה: ✅ מסכימים! | {דעה_שנייה['תחזית']} | יחסים: בית {דעה_שנייה['מכרז_בית']} | תיקו {דעה_שנייה['מכרז_תיקו']} | חוץ {דעה_שנייה['מכרז_חוץ']}")
        else:
            st.warning(f"🔮 דעה שנייה: ⚠️ חלוקי דעות | {דעה_שנייה['תחזית']} | יחסים: בית {דעה_שנייה['מכרז_בית']} | תיקו {דעה_שנייה['מכרז_תיקו']} | חוץ {דעה_שנייה['מכרז_חוץ']}")
    
    st.markdown("---")
    if צבע == "green":
        st.success(f"🎯 המלצה: {המלצה} | 💪 ביטחון: {ביטחון}")
    else:
        st.warning(f"🎯 המלצה: {המלצה} | 💪 ביטחון: {ביטחון}")
