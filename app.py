import streamlit as st
import json
import os
import random
import urllib.request
from collections import Counter
from datetime import datetime

# --- [UI 설정] 스마트폰 화면에 맞춘 설정 ---
st.set_page_config(page_title="AI 로또 분석기", page_icon="🎰", layout="centered")

# CSS를 활용해 로또 번호를 시각적인 공 모양으로 렌더링
st.markdown("""
<style>
.lotto-ball {
    display: inline-block;
    width: 40px;
    height: 40px;
    line-height: 40px;
    border-radius: 50%;
    text-align: center;
    color: white;
    font-weight: bold;
    font-size: 16px;
    margin: 2px;
    box-shadow: 1px 1px 3px rgba(0,0,0,0.2);
}
.ball-yellow { background-color: #fbc400; color: #333; }
.ball-blue { background-color: #69c8f2; color: #333; }
.ball-red { background-color: #ff7272; }
.ball-gray { background-color: #aaaaaa; }
.ball-green { background-color: #b0d840; color: #333; }
</style>
""", unsafe_allow_html=True)

def get_ball_color(num):
    if num <= 10: return "ball-yellow"
    elif num <= 20: return "ball-blue"
    elif num <= 30: return "ball-red"
    elif num <= 40: return "ball-gray"
    else: return "ball-green"

def render_lotto_balls(numbers):
    html = ""
    for num in numbers:
        color_class = get_ball_color(num)
        html += f'<div class="lotto-ball {color_class}">{num:02d}</div>'
    return f"<div>{html}</div>"

# --- [핵심 로직] 기존 코드 재사용 (출력을 반환으로 변경) ---
CACHE_FILE = "lotto_history_cache.json"

def get_latest_draw_no() -> int:
    first_draw_time = datetime(2002, 12, 7, 20, 45)
    now = datetime.now()
    diff = now - first_draw_time
    return max(1, diff.days // 7 + 1)

def load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return {int(k): v for k, v in json.load(f).items()}
        except Exception:
            return {}
    return {}

def save_cache(cache_data: dict):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)

def fetch_lotto_draw(draw_no: int) -> list[int] | None:
    url = f"https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo={draw_no}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                if data.get("returnValue") == "success":
                    return [data[f"drwtNo{i}"] for i in range(1, 7)]
    except:
        pass
    return None

def collect_history_data(latest_draw_no: int, total_weeks: int = 52):
    cache = load_cache()
    target_draws = list(range(latest_draw_no - total_weeks + 1, latest_draw_no + 1))
    missing_draws = [d for d in target_draws if d not in cache]

    if missing_draws:
        for d in missing_draws:
            nums = fetch_lotto_draw(d)
            if nums:
                cache[d] = nums
        save_cache(cache)
    return [cache[d] for d in target_draws if d in cache]

def analyze_period(history_data: list[list[int]]):
    all_numbers = []
    sums = []
    odds, highs = 0, 0
    total = len(history_data)

    if total == 0: return None

    for draw in history_data:
        all_numbers.extend(draw)
        sums.append(sum(draw))
        for n in draw:
            if n % 2 != 0: odds += 1
            if n >= 23: highs += 1

    counts = Counter(all_numbers)
    full_freq = {n: counts.get(n, 0) for n in range(1, 46)}
    
    return {
        "avg_odd": odds / total,
        "avg_high": highs / total,
        "avg_sum": sum(sums) / total,
        "frequency": full_freq
    }

def weighted_sample(population, weights, k):
    keys = [random.random() ** (1.0 / max(w, 0.001)) for w in weights]
    sorted_items = [item for _, item in sorted(zip(keys, population), reverse=True)]
    return sorted_items[:k]

def generate_5_combinations(history_1w, history_26w, history_52w, stats_52w):
    target_odd = round(stats_52w["avg_odd"])
    target_high = round(stats_52w["avg_high"])
    target_sum = round(stats_52w["avg_sum"])
    sum_tolerance = 15

    freq_1w = Counter([n for d in history_1w for n in d])
    freq_26w = Counter([n for d in history_26w for n in d])
    freq_52w = Counter([n for d in history_52w for n in d])

    scores = {}
    for n in range(1, 46):
        scores[n] = (freq_52w.get(n, 0) * 1.0) + (freq_26w.get(n, 0) * 1.5) + (freq_1w.get(n, 0) * 2.0) + 1.0

    population = list(range(1, 46))
    weights = [scores[n] for n in population]
    last_week_numbers = history_1w[-1] if history_1w else []
    cold_pool_26w = [n for n in range(1, 46) if freq_26w.get(n, 0) <= 2]

    strategies = [
        ("게임 A [다빈도 핫넘버 집중형]", "최근 6개월 및 1년간 출현 빈도가 높은 상위 번호군 중심"),
        ("게임 B [황금 밸런스형]", "홀짝, 고저, 평균 총합을 맞춘 최적 균형형"),
        ("게임 C [직전 회차 이월 연계형]", "직전 당첨 번호 1개 이월수 포함 + 다빈도수 조합"),
        ("게임 D [미출현 반등 조화형]", "최근 6개월 출현이 적었던 번호 1개 반등 기대"),
        ("게임 E [종합 가중치 추천형]", "1주·6개월·1년 빈도 종합 점수 기반 최적 조합")
    ]

    results = []
    generated_combos = set()

    for idx, (title, desc) in enumerate(strategies):
        for _ in range(5000):
            if idx == 0:
                top_pool = sorted(population, key=lambda n: scores[n], reverse=True)[:24]
                combo = sorted(weighted_sample(top_pool, [scores[n] for n in top_pool], 6))
            elif idx == 2 and last_week_numbers:
                carry = random.choice(last_week_numbers)
                rem_pop = [n for n in population if n != carry]
                combo = sorted([carry] + weighted_sample(rem_pop, [scores[n] for n in rem_pop], 5))
            elif idx == 3 and cold_pool_26w:
                cold = random.choice(cold_pool_26w)
                rem_pop = [n for n in population if n != cold]
                combo = sorted([cold] + weighted_sample(rem_pop, [scores[n] for n in rem_pop], 5))
            else:
                combo = sorted(weighted_sample(population, weights, 6))

            if any(combo[i+3] - combo[i] == 3 for i in range(3)): continue
            
            combo_tuple = tuple(combo)
            if combo_tuple in generated_combos: continue

            odds = sum(1 for n in combo if n % 2 != 0)
            highs = sum(1 for n in combo if n >= 23)
            c_sum = sum(combo)

            if odds == target_odd and highs == target_high and abs(c_sum - target_sum) <= sum_tolerance:
                generated_combos.add(combo_tuple)
                results.append((title, desc, combo, odds, highs, c_sum))
                break
    return results, target_odd, target_high, target_sum


# --- [Streamlit 화면 구성] ---
st.title("🎰 통계 기반 로또 분석기")
st.write("동행복권 API와 통계 알고리즘을 활용하여 최적의 조합을 추출합니다.")

latest_draw = get_latest_draw_no()
st.info(f"현재 최신 회차: **제 {latest_draw} 회**")

# 터치하기 편한 큰 버튼 생성
if st.button("통계 분석 및 맞춤 번호 추출하기", use_container_width=True, type="primary"):
    with st.spinner("52주간의 당첨 데이터를 분석 중입니다..."):
        
        # 1. 데이터 수집
        history_52_weeks = collect_history_data(latest_draw, 52)
        
        # 2. 데이터 분할 및 통계 산출
        data_1w = history_52_weeks[-1:]
        data_26w = history_52_weeks[-26:]
        stats_52w = analyze_period(history_52_weeks)

        if not stats_52w:
            st.error("데이터 수집에 실패했습니다. 인터넷 연결을 확인해주세요.")
            st.stop()

        # 3. 5조합 생성
        results, t_odd, t_high, t_sum = generate_5_combinations(data_1w, data_26w, history_52_weeks, stats_52w)

    st.success("✅ 분석 및 조합 추출이 완료되었습니다!")

    # 4. 결과 출력
    st.subheader(f"🎯 5가지 전략 추천 조합")
    st.caption(f"목표 통계: 홀{t_odd}:짝{6-t_odd} | 저{6-t_high}:고{t_high} | 평균총합 {t_sum}")
    
    st.divider()

    for title, desc, combo, odds, highs, c_sum in results:
        st.markdown(f"**{title}**")
        st.caption(desc)
        
        # 직관적인 로또 공 렌더링
        st.markdown(render_lotto_balls(combo), unsafe_allow_html=True)
        
        # 통계 지표 박스
        st.markdown(f"""
        <div style='background-color:#f0f2f6; padding:10px; border-radius:8px; margin-top:10px; margin-bottom:20px; font-size:14px; color:#555;'>
            📊 홀 <b>{odds}</b> : 짝 <b>{6-odds}</b> &nbsp;|&nbsp; 
            저 <b>{6-highs}</b> : 고 <b>{highs}</b> &nbsp;|&nbsp; 
            총합: <b>{c_sum}</b>
        </div>
        """, unsafe_allow_html=True)