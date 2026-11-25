"""Task 5 – Trợ lý AI hỗ trợ vận hành CLB.

4 chức năng:
  1. draft_announcement  – soạn nháp thông báo
  2. summarize_minutes   – tóm tắt biên bản họp (quyết định, việc cần làm, vấn đề)
  3. suggest_assignment  – đề xuất người phù hợp để giao việc (chấm điểm dựa trên dữ liệu)
  4. engagement_report   – phát hiện thành viên ít tương tác

Cơ chế: nếu có GEMINI_API_KEY / OPENAI_API_KEY -> gọi LLM qua REST API (thư viện requests).
Nếu không có key hoặc gọi lỗi -> dùng bộ xử lý nội bộ (rule-based/thống kê), nên app luôn chạy được.
Mọi nội dung AI sinh ra đều là BẢN NHÁP, phải được người có quyền duyệt mới công bố
(xem blueprints/ai.py) – đúng lưu đồ "AI nháp rồi duyệt".
"""
import re
from collections import Counter
from datetime import datetime, timedelta

from flask import current_app

from .db import query

SYSTEM_PROMPT = ("Bạn là trợ lý vận hành của một câu lạc bộ sinh viên Việt Nam. "
                 "Luôn trả lời bằng tiếng Việt, ngắn gọn, rõ ràng, đúng sự thật được cung cấp, "
                 "không bịa thêm thông tin (ngày giờ, địa điểm, tên người) nếu không có trong dữ liệu.")

STOPWORDS = set("""và là của có cho các những được trong với không này đó khi thì để một như cũng đã sẽ
đang rất nhiều về theo từ tại ra vào lại nên bạn mình chúng ta chúng tôi họ người việc làm cần
nhưng hay hoặc nếu vì bị đến trên dưới sau trước còn mới thêm nữa nào gì ai đây vậy rồi lúc
ạ nhé nha thôi thế""".split())

DECISION_KW = ["thống nhất", "quyết định", "chốt", "đồng ý", "thông qua", "phê duyệt", "kết luận"]
ACTION_KW = ["phụ trách", "giao cho", "chịu trách nhiệm", "deadline", "hạn chót", "trước ngày", "hoàn thành trước",
             "nhiệm vụ", "cần chuẩn bị", "sẽ làm", "lo phần", "đảm nhận", "liên hệ", "gửi", "nộp"]
ISSUE_KW = ["vấn đề", "khó khăn", "thiếu", "chưa có", "chưa xong", "lo ngại", "rủi ro", "vướng", "trễ", "chậm"]


# ======================================================================
# Gọi LLM
# ======================================================================
class LLMError(Exception):
    pass


def provider_name():
    cfg = current_app.config
    if cfg.get("GEMINI_API_KEY"):
        return "gemini"
    if cfg.get("OPENAI_API_KEY"):
        return "openai"
    return "local"


def call_llm(prompt, system=SYSTEM_PROMPT):
    """Gọi LLM, trả về text. Ném LLMError nếu không có key / lỗi mạng."""
    import requests
    cfg = current_app.config
    p = provider_name()
    try:
        if p == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{cfg['GEMINI_MODEL']}:generateContent"
            resp = requests.post(url, headers={"x-goog-api-key": cfg["GEMINI_API_KEY"]}, timeout=cfg["AI_TIMEOUT"],
                                 json={"systemInstruction": {"parts": [{"text": system}]},
                                       "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                                       "generationConfig": {"temperature": 0.5}})
            resp.raise_for_status()
            parts = resp.json()["candidates"][0]["content"]["parts"]
            return "".join(x.get("text", "") for x in parts).strip()
        if p == "openai":
            resp = requests.post("https://api.openai.com/v1/chat/completions", timeout=cfg["AI_TIMEOUT"],
                                 headers={"Authorization": f"Bearer {cfg['OPENAI_API_KEY']}"},
                                 json={"model": cfg["OPENAI_MODEL"], "temperature": 0.5,
                                       "messages": [{"role": "system", "content": system},
                                                    {"role": "user", "content": prompt}]})
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:  # mạng lỗi, key sai, hết quota...
        raise LLMError(str(exc)[:200]) from exc
    raise LLMError("Chưa cấu hình API key")


def _try_llm(prompt):
    """Trả (text, provider) hoặc (None, lý do lỗi)."""
    if provider_name() == "local":
        return None, "local"
    try:
        text = call_llm(prompt)
        if text:
            return text, provider_name()
        return None, "local (LLM trả rỗng)"
    except LLMError as e:
        current_app.logger.warning("LLM lỗi, chuyển sang xử lý nội bộ: %s", e)
        return None, "local (LLM lỗi)"


# ======================================================================
# 1. Soạn nháp thông báo
# ======================================================================
TONES = {
    "formal": "trang trọng",
    "friendly": "thân thiện",
    "exciting": "hào hứng, truyền cảm hứng",
}


def draft_announcement(topic, details="", audience="toàn thể thành viên", tone="friendly", club_name="CLB"):
    prompt = (f"Soạn một thông báo của {club_name} gửi {audience}.\n"
              f"Chủ đề: {topic}\nThông tin chi tiết (chỉ dùng các thông tin này):\n{details or '(không có)'}\n"
              f"Giọng văn: {TONES.get(tone, 'thân thiện')}.\n"
              "Yêu cầu: dòng đầu là tiêu đề (không có ký hiệu markdown), sau đó là nội dung 120–200 từ, "
              "có lời chào, các ý chính dạng gạch đầu dòng, lời kêu gọi hành động và ký tên Ban Chủ nhiệm.")
    text, provider = _try_llm(prompt)
    if text:
        return text.replace("**", ""), provider
    return _local_announcement(topic, details, audience, tone, club_name), provider


def _local_announcement(topic, details, audience, tone, club_name):
    greet = {"formal": f"Kính gửi {audience},",
             "friendly": f"Chào {audience} thân mến,",
             "exciting": f"Hello {audience} ơi! 🎉"}.get(tone, f"Chào {audience},")
    intro = {"formal": f"Ban Chủ nhiệm {club_name} trân trọng thông báo về: {topic}.",
             "friendly": f"{club_name} gửi đến mọi người thông tin về {topic.lower()} nè.",
             "exciting": f"Sự kiện được mong chờ nhất đã đến: {topic}! 🚀"}.get(tone, topic)
    lines = [ln.strip(" -•\t") for ln in re.split(r"[\n;]+", details or "") if ln.strip(" -•\t")]
    bullets = "\n".join(f"• {ln[0].upper() + ln[1:]}" for ln in lines) or "• Thông tin chi tiết sẽ được cập nhật sau."
    cta = {"formal": "Đề nghị các thành viên sắp xếp thời gian tham gia đầy đủ.",
           "friendly": "Mọi người nhớ đăng ký trên ClubHub và rủ thêm bạn bè nhé!",
           "exciting": "Đăng ký ngay trên ClubHub kẻo lỡ nha! 🔥"}.get(tone, "")
    return (f"[Thông báo] {topic}\n\n{greet}\n\n{intro}\n\n{bullets}\n\n{cta}\n\n"
            f"Mọi thắc mắc vui lòng liên hệ Ban Chủ nhiệm.\nTrân trọng,\nBan Chủ nhiệm {club_name}")


# ======================================================================
# 2. Tóm tắt biên bản họp
# ======================================================================
def summarize_minutes(notes):
    prompt = ("Tóm tắt biên bản cuộc họp CLB dưới đây theo đúng 4 mục, mỗi mục là các gạch đầu dòng '- ':\n"
              "TÓM TẮT CHÍNH\nQUYẾT ĐỊNH\nVIỆC CẦN LÀM (ghi rõ người phụ trách và hạn nếu có)\nVẤN ĐỀ CẦN THEO DÕI\n"
              "Nếu mục nào không có thông tin thì ghi '- Không có'.\n\nBIÊN BẢN:\n" + notes)
    text, provider = _try_llm(prompt)
    if text:
        return text.replace("**", ""), provider
    return _local_summary(notes), provider


def _sentences(text):
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip(" -•*\t") for p in parts if len(p.strip(" -•*\t")) > 3]


def _words(s):
    return [w for w in re.findall(r"[\wÀ-ỹ]+", s.lower()) if w not in STOPWORDS and len(w) > 1 and not w.isdigit()]


def _local_summary(notes):
    sents = _sentences(notes)
    if not sents:
        return "TÓM TẮT CHÍNH\n- Không có nội dung."
    has = lambda s, kws: any(k in s.lower() for k in kws)  # noqa: E731
    decisions = [s for s in sents if has(s, DECISION_KW)]
    actions = [s for s in sents if has(s, ACTION_KW) and s not in decisions]
    issues = [s for s in sents if has(s, ISSUE_KW) and s not in decisions and s not in actions]

    # Tóm tắt trích xuất: chấm điểm câu theo tần suất từ khóa (TF)
    freq = Counter(w for s in sents for w in _words(s))
    top = max(freq.values()) if freq else 1
    scored = []
    for i, s in enumerate(sents):
        ws = _words(s)
        if not ws:
            continue
        score = sum(freq[w] / top for w in ws) / (len(ws) ** 0.5)
        if i == 0:
            score *= 1.2  # câu mở đầu thường nêu mục đích họp
        scored.append((score, i, s))
    n = max(2, min(5, len(sents) // 3))
    key = [s for _, i, s in sorted(sorted(scored, reverse=True)[:n], key=lambda x: x[1])]

    dates = sorted(set(re.findall(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b", notes)))

    def block(title, items):
        return title + "\n" + ("\n".join(f"- {x}" for x in items) if items else "- Không có")

    out = [block("TÓM TẮT CHÍNH", key), block("QUYẾT ĐỊNH", decisions),
           block("VIỆC CẦN LÀM", actions), block("VẤN ĐỀ CẦN THEO DÕI", issues)]
    if dates:
        out.append("MỐC THỜI GIAN NHẮC ĐẾN\n- " + ", ".join(dates))
    return "\n\n".join(out)


# ======================================================================
# 3. Đề xuất phân công
# ======================================================================
def _member_stats(since):
    """Thống kê hoạt động của từng thành viên từ ngày `since`."""
    return query("""
        SELECT m.id, m.full_name, m.student_id, m.department_id, d.name AS department_name, m.joined_at, m.last_login,
          (SELECT COUNT(*) FROM tasks t WHERE t.assignee_id=m.id AND t.status!='done') AS open_tasks,
          (SELECT COUNT(*) FROM tasks t WHERE t.assignee_id=m.id) AS total_tasks,
          (SELECT COUNT(*) FROM tasks t WHERE t.assignee_id=m.id AND t.status='done') AS done_tasks,
          (SELECT COUNT(*) FROM tasks t WHERE t.assignee_id=m.id AND t.status!='done'
              AND t.deadline < date('now','localtime')) AS overdue_tasks,
          (SELECT COUNT(*) FROM events e WHERE e.start_time >= :since AND e.start_time < datetime('now','localtime')
              AND e.start_time >= m.joined_at) AS eligible_events,
          (SELECT COUNT(*) FROM registrations r JOIN events e ON e.id=r.event_id WHERE r.member_id=m.id
              AND e.start_time >= :since AND e.start_time < datetime('now','localtime')) AS registered,
          (SELECT COUNT(*) FROM registrations r JOIN events e ON e.id=r.event_id WHERE r.member_id=m.id
              AND e.start_time >= :since AND r.checked_in_at IS NOT NULL) AS attended,
          (SELECT MAX(r.checked_in_at) FROM registrations r WHERE r.member_id=m.id) AS last_checkin,
          (SELECT MAX(t.completed_at) FROM tasks t WHERE t.assignee_id=m.id) AS last_done,
          (SELECT GROUP_CONCAT(t.title, ' | ') FROM tasks t WHERE t.assignee_id=m.id AND t.status='done') AS done_titles
        FROM members m JOIN roles r ON r.id=m.role_id LEFT JOIN departments d ON d.id=m.department_id
        WHERE m.is_active=1 AND r.code!='admin'""", {"since": since})


def suggest_assignment(title, description="", department_id=None, top_n=5):
    since = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    stats = _member_stats(since)
    if department_id:
        stats = [s for s in stats if s["department_id"] == department_id] or stats
    task_words = set(_words(f"{title} {description}"))
    cands = []
    for s in stats:
        done_rate = s["done_tasks"] / s["total_tasks"] if s["total_tasks"] else 0.6
        att_rate = s["attended"] / s["eligible_events"] if s["eligible_events"] else 0.5
        exp_words = set(_words(s["done_titles"] or ""))
        overlap = len(task_words & exp_words)
        experience = min(1.0, overlap / max(1, min(3, len(task_words))))
        workload = 1 - min(s["open_tasks"], 5) / 5
        score = 35 * workload + 25 * done_rate + 15 * min(att_rate, 1) + 25 * experience - 8 * min(s["overdue_tasks"], 2)
        reasons = []
        reasons.append(f"đang có {s['open_tasks']} việc chưa xong" if s["open_tasks"] else "hiện không có việc tồn")
        if s["total_tasks"]:
            reasons.append(f"hoàn thành {s['done_tasks']}/{s['total_tasks']} việc ({round(done_rate * 100)}%)")
        if overlap:
            reasons.append("đã từng làm việc tương tự")
        if s["eligible_events"]:
            reasons.append(f"tham gia {s['attended']}/{s['eligible_events']} sự kiện gần đây")
        if s["overdue_tasks"]:
            reasons.append(f"⚠ {s['overdue_tasks']} việc quá hạn")
        cands.append({**dict(s), "score": round(max(score, 0), 1), "reasons": reasons})
    cands.sort(key=lambda c: c["score"], reverse=True)
    cands = cands[:top_n]

    explanation, provider = None, "local"
    if cands and provider_name() != "local":
        table = "\n".join(f"- {c['full_name']} ({c['department_name']}): điểm {c['score']}; " + "; ".join(c["reasons"])
                          for c in cands)
        explanation, provider = _try_llm(
            f"Cần giao công việc: '{title}'. Mô tả: {description or '(không có)'}.\n"
            f"Các ứng viên đã được hệ thống chấm điểm:\n{table}\n"
            "Hãy chọn 1 người phù hợp nhất và 1 người dự phòng, giải thích ngắn gọn trong 3-4 câu.")
    if not explanation and cands:
        best = cands[0]
        explanation = (f"Đề xuất giao cho {best['full_name']} vì {', '.join(best['reasons'][:3])}."
                       + (f" Dự phòng: {cands[1]['full_name']}." if len(cands) > 1 else ""))
    return cands, explanation, provider


# ======================================================================
# 4. Phát hiện thành viên ít tương tác
# ======================================================================
def engagement_report(days=90):
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    now = datetime.now()
    rows = []
    for s in _member_stats(since):
        att_rate = s["attended"] / s["eligible_events"] if s["eligible_events"] else None
        task_rate = s["done_tasks"] / s["total_tasks"] if s["total_tasks"] else None
        last = max([x for x in (s["last_checkin"], s["last_done"], s["last_login"]) if x] or [s["joined_at"]])
        try:
            days_inactive = (now - datetime.strptime(last[:10], "%Y-%m-%d")).days
        except ValueError:
            days_inactive = 0
        recency = max(0.0, 1 - days_inactive / 60)
        score = 50 * (att_rate if att_rate is not None else 0.5) + \
            25 * (task_rate if task_rate is not None else 0.6) + 25 * recency
        reasons = []
        if s["eligible_events"]:
            missed = s["eligible_events"] - s["attended"]
            if missed:
                reasons.append(f"vắng {missed}/{s['eligible_events']} sự kiện")
        no_show = s["registered"] - s["attended"]
        if no_show >= 1:
            reasons.append(f"đăng ký nhưng không đến {no_show} lần")
        if s["overdue_tasks"]:
            reasons.append(f"{s['overdue_tasks']} việc quá hạn")
        if days_inactive > 21:
            reasons.append(f"không có hoạt động {days_inactive} ngày")
        level = "low" if score < 40 else ("watch" if score < 60 else "ok")
        rows.append({**dict(s), "score": round(score), "level": level, "reasons": reasons,
                     "att_rate": att_rate, "task_rate": task_rate, "days_inactive": days_inactive,
                     "suggestion": _suggest_action(level, s, days_inactive)})
    rows.sort(key=lambda r: r["score"])
    return rows


def _suggest_action(level, s, days_inactive):
    if level == "ok":
        return "Duy trì; có thể giao vai trò nòng cốt."
    if s["overdue_tasks"]:
        return "Trưởng ban trao đổi riêng về khối lượng việc, cân nhắc chia nhỏ hoặc chuyển việc."
    if days_inactive > 45:
        return "Nhắn tin hỏi thăm, mời tham gia sự kiện nhẹ nhàng sắp tới (workshop/team building)."
    return "Gợi ý ghép cặp với thành viên tích cực, giao việc nhỏ có thời hạn ngắn."


def checkin_message(member_name, reasons, club_name="CLB"):
    """Soạn tin nhắn hỏi thăm thành viên ít tương tác (để trưởng ban gửi)."""
    text, provider = _try_llm(
        f"Soạn tin nhắn Messenger ngắn (50-80 từ), ấm áp, không trách móc, gửi bạn {member_name} – thành viên {club_name} "
        f"dạo này ít tham gia ({'; '.join(reasons) or 'ít hoạt động'}). Hỏi thăm, hỏi có khó khăn gì không "
        "và mời tham gia hoạt động sắp tới.")
    if text:
        return text, provider
    first = member_name.split()[-1]
    return (f"Hi {first}, dạo này {first} ổn không? Lâu rồi không thấy {first} ghé {club_name}, mọi người nhớ lắm 😊. "
            f"Nếu đang bận học hay có khó khăn gì cứ chia sẻ với mình nhé, CLB sẵn sàng hỗ trợ. "
            f"Sắp tới có hoạt động mới, {first} tham gia cùng mọi người cho vui nha!"), provider
