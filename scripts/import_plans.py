#!/usr/bin/env python3
"""
Pobiera listę oddziałów i ich plany z witryny ZS1, a następnie zapisuje
ujednoliconą bazę data/lessons.json.

Parser celowo przerywa synchronizację, jeśli nie potrafi rozpoznać struktury
strony. Dzięki temu błędny/niepełny import nie nadpisze poprzedniej bazy.
"""
from __future__ import annotations
import json, re, sys, tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

BASE = "https://zs-1.edu.pl/plany/uczniowie/"
LIST_URL = urljoin(BASE, "lista.html")
CHANGES_URL = "https://www.zs-1.edu.pl/index.php/plan-lekcji/zmiany-do-planu"
OUTPUT = Path(__file__).resolve().parents[1] / "data" / "lessons.json"
DAYS = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek"]
WARSAW = ZoneInfo("Europe/Warsaw")
HEADERS = {"User-Agent": "TeacherFinder/1.0 (school timetable index; respectful weekly fetch)"}
TIME_RE = re.compile(r"^\s*(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})\s*$")
GROUP_RE = re.compile(r"(?:[- ]([12]/2))$")
CHANGE_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
CLASS_HEADING_RE = re.compile(r"\d{1,2}[A-Z]{1,2}", re.IGNORECASE)
LESSON_CHANGE_RE = re.compile(r"^\s*Lekcja\s+((?:\d+\s*,\s*)*\d+)\b(.*)$", re.IGNORECASE)
CHANGE_GROUP_RE = re.compile(r"\bgrupa\s+([\w/]+)", re.IGNORECASE)
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

def fetch(url: str) -> str:
    response = SESSION.get(url, timeout=30)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text

def current_week_start(today: date | None = None) -> date:
    today = today or datetime.now(WARSAW).date()
    monday = today - timedelta(days=today.weekday())
    return monday + timedelta(days=7) if today.weekday() == 6 else monday

def merge_week_changes(fresh_changes, existing_changes, week_start: date):
    week_end = week_start + timedelta(days=4)

    def in_week(change):
        try:
            change_date = date.fromisoformat(change["date"])
        except (KeyError, TypeError, ValueError):
            return False
        return week_start <= change_date <= week_end

    merged = {}
    for change in existing_changes:
        if in_week(change):
            key = (
                change["date"],
                change["class_name"],
                change.get("lesson_number"),
                change.get("group", ""),
                change.get("original_text", "") if change.get("lesson_number") is None else "",
            )
            merged[key] = change
    for change in fresh_changes:
        if in_week(change):
            key = (
                change["date"],
                change["class_name"],
                change.get("lesson_number"),
                change.get("group", ""),
                change.get("original_text", "") if change.get("lesson_number") is None else "",
            )
            merged[key] = change
    return list(merged.values())

def get_classes(html: str):
    soup = BeautifulSoup(html, "html.parser")
    found = []
    for link in soup.select("a[href]"):
        href = link.get("href", "").strip()
        label = " ".join(link.get_text(" ", strip=True).split())
        if re.fullmatch(r"plany/o\d+\.html", href) and label:
            found.append({"class_name": label.split()[0].upper(), "label": label, "url": urljoin(BASE, href)})
    # Remove duplicate hrefs while preserving order.
    unique = {item["url"]: item for item in found}
    if not unique:
        raise RuntimeError("Nie znaleziono linków plany/oN.html na liście oddziałów.")
    return list(unique.values())

def cell_lines(cell):
    # Explicit <br> elements separate group entries. Inline formatting (e.g. <b>)
    # must not split a single entry into multiple fragments.
    from bs4 import NavigableString
    fragment = BeautifulSoup(str(cell), "html.parser")
    for br in fragment.find_all("br"):
        br.replace_with(NavigableString(" __TF_BREAK__ "))
    raw = fragment.get_text(" ", strip=True)
    return [" ".join(line.split()) for line in raw.split("__TF_BREAK__") if line.strip()]

def parse_lesson_line(line: str):
    line = re.sub(r"\s+", " ", line).strip()
    tokens = line.split()
    if len(tokens) < 3:
        return None
    # Optivum entries end in: subject, teacher code, room.
    room = tokens[-1]
    teacher = tokens[-2]
    subject = " ".join(tokens[:-2]).strip()
    if not subject or not re.fullmatch(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż#]{1,5}", teacher):
        return None
    group_match = GROUP_RE.search(subject)
    group = group_match.group(1) if group_match else ""
    subject = GROUP_RE.sub("", subject).strip()
    return {"subject": subject, "teacher": teacher, "room": room, "group": group}

def parse_plan(html: str, class_name: str):
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        raise RuntimeError(f"{class_name}: nie znaleziono tabeli planu.")
    # Choose the table with a header containing weekday names.
    table = None
    for candidate in tables:
        text = candidate.get_text(" ", strip=True).lower()
        if "poniedziałek" in text and "piątek" in text:
            table = candidate
            break
    if table is None:
        raise RuntimeError(f"{class_name}: nie rozpoznano tabeli tygodniowej.")
    rows = table.find_all("tr")
    lessons = []
    recognized_rows = 0
    for row in rows:
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) < 7:
            continue
        values = [c.get_text(" ", strip=True) for c in cells]
        # The time column is normally the second cell.
        time_value = values[1] if len(values) > 1 else ""
        time_match = TIME_RE.match(time_value)
        if not time_match:
            continue
        recognized_rows += 1
        lesson_number = re.sub(r"\D", "", values[0]) or str(recognized_rows)
        for day_index in range(5):
            cell_index = day_index + 2
            if cell_index >= len(cells):
                continue
            for line in cell_lines(cells[cell_index]):
                parsed = parse_lesson_line(line)
                if not parsed:
                    continue
                lessons.append({
                    "class_name": class_name,
                    "day": DAYS[day_index],
                    "day_index": day_index,
                    "lesson_number": int(lesson_number),
                    "time": f"{time_match.group(1)}–{time_match.group(2)}",
                    **parsed
                })
    if recognized_rows < 5:
        raise RuntimeError(f"{class_name}: rozpoznano tylko {recognized_rows} wierszy godzinowych.")
    return lessons

def make_change(date: str, class_name: str, lesson_number: int | None,
                group: str, action: str, original_text: str, **fields):
    return {
        "date": date,
        "class_name": class_name,
        "lesson_number": lesson_number,
        "group": group,
        "action": action,
        "new_subject": None,
        "new_teacher": None,
        "new_room": None,
        "moved": False,
        "moved_from": None,
        "original_text": original_text,
        "display_notice": False,
        **fields,
    }

def parse_change_line(date: str, class_name: str, text: str):
    start_match = re.search(
        r"\b(?:grupa\s+([\w/]+)\s+)?rozpoczyna\s+zajęcia\s+od\s+lekcji\s+(\d+)",
        text,
        re.IGNORECASE,
    )
    if start_match:
        group = start_match.group(1) or ""
        first_lesson = int(start_match.group(2))
        changes = [
            make_change(date, class_name, number, group, "cancel", text)
            for number in range(1, first_lesson)
        ]
        if changes:
            changes[0]["display_notice"] = True
        return changes

    dismissal_match = re.search(
        r"\b(?:grupa\s+([\w/]+)|klasa)\s+zwolniona\s+do\s+domu\s+po\s+lekcji\s+(\d+)",
        text,
        re.IGNORECASE,
    )
    if dismissal_match:
        group = dismissal_match.group(1) or ""
        last_lesson = int(dismissal_match.group(2))
        changes = [
            make_change(date, class_name, number, group, "cancel", text)
            for number in range(last_lesson + 1, 13)
        ]
        if changes:
            changes[0]["display_notice"] = True
        return changes

    lesson_match = LESSON_CHANGE_RE.match(text)
    if not lesson_match:
        return [make_change(date, class_name, None, "", "note", text)]

    lesson_numbers = [int(value.strip()) for value in lesson_match.group(1).split(",")]
    description = lesson_match.group(2).strip()
    group_match = CHANGE_GROUP_RE.search(description)
    group = group_match.group(1) if group_match else ""
    if group_match:
        description = description[:group_match.start()] + description[group_match.end():]
    description = re.sub(r"\bcałość\b", "", description, flags=re.IGNORECASE)
    description = description.strip(" \t–—-:;")

    if re.search(r"\b(?:odwołan\w*|nie\s+ma\s+zajęć|brak\s+zajęć)\b", description, re.IGNORECASE):
        return [
            make_change(date, class_name, number, group, "cancel", text)
            for number in lesson_numbers
        ]

    moved_match = re.search(r"\bzajęcia\s+przeniesione\s+z\s+(.+)$", description, re.IGNORECASE)
    moved_from = moved_match.group(1).strip(" .") if moved_match else None
    details = description[:moved_match.start()].strip(" \t–—-:;") if moved_match else description
    teacher_match = re.search(r"\bp\.\s*(.+?)(?=\s+s\.|$)", details, re.IGNORECASE)
    room_match = re.search(r"\bs\.\s*(.+)$", details, re.IGNORECASE)
    new_teacher = teacher_match.group(1).strip(" ,;") if teacher_match else None
    new_room = room_match.group(1).strip(" ,;") if room_match else None

    field_positions = [
        match.start() for match in (teacher_match, room_match) if match is not None
    ]
    subject = details[:min(field_positions)].strip(" \t–—-:;") if field_positions else details
    subject = re.sub(r"^zastępstwo\b\s*", "", subject, flags=re.IGNORECASE).strip(" \t–—-:;")
    new_subject = subject or None

    action = "replace" if new_subject or new_teacher or new_room or moved_from else "note"
    return [
        make_change(
            date,
            class_name,
            number,
            group,
            action,
            text,
            new_subject=new_subject,
            new_teacher=new_teacher,
            new_room=new_room,
            moved=bool(moved_from),
            moved_from=moved_from,
        )
        for number in lesson_numbers
    ]

def parse_changes(html: str):
    soup = BeautifulSoup(html, "html.parser")
    article = soup.select_one("article#article-20") or soup.select_one("article.uk-article")
    if article is None:
        raise RuntimeError("Nie znaleziono artykułu ze zmianami planu.")

    content = article.select_one('[property="text"]') or article
    changes = []
    current_date = None
    class_name = None
    has_content = False
    found_date = False
    for node in content.find_all(["h2", "h3", "h4", "p"]):
        text = " ".join(node.get_text(" ", strip=True).split())
        if node.name in ("h2", "h3", "h4"):
            date_match = CHANGE_DATE_RE.search(text)
            if date_match:
                current_date = date_match.group(1)
                try:
                    datetime.strptime(current_date, "%Y-%m-%d")
                except ValueError as exc:
                    raise RuntimeError(f"Nieprawidłowa data zmian: {current_date}") from exc
                class_name = None
                found_date = True
            continue
        if not text:
            continue
        has_content = True
        if not current_date:
            continue
        if CLASS_HEADING_RE.fullmatch(text):
            class_name = text.upper()
            continue
        if not class_name:
            raise RuntimeError(f"Nie rozpoznano klasy przy wpisie zmian: {text}")
        changes.extend(parse_change_line(current_date, class_name, text))

    if has_content and not found_date:
        raise RuntimeError("Nie znaleziono daty w sekcji zmian planu.")
    return changes

def main(changes_only=False):
    now = datetime.now(timezone.utc)
    week_start = current_week_start()
    existing_payload = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {}
    existing_meta = existing_payload.get("meta", {})

    if changes_only:
        all_lessons = existing_payload.get("lessons", [])
        if not isinstance(all_lessons, list) or len(all_lessons) < 20:
            raise RuntimeError("Nie ma kompletnego planu; najpierw uruchom pełną synchronizację.")
        classes = existing_meta.get("classes", [])
        print(f"Zachowuję plan tygodnia i odświeżam zmiany dla tygodnia od {week_start}.")
    else:
        print(f"Pobieram listę oddziałów: {LIST_URL}")
        classes = get_classes(fetch(LIST_URL))
        print(f"Znaleziono {len(classes)} oddziałów.")
        all_lessons, errors = [], []
        for item in classes:
            try:
                parsed = parse_plan(fetch(item["url"]), item["class_name"])
                if not parsed:
                    raise RuntimeError("Plan nie zawiera rozpoznanych lekcji.")
                all_lessons.extend(parsed)
                print(f"OK {item['class_name']}: {len(parsed)} wpisów")
            except Exception as exc:
                errors.append(f"{item['class_name']}: {exc}")
                print(f"BŁĄD {item['class_name']}: {exc}", file=sys.stderr)

        # Fail closed: don't publish a partial snapshot if any class failed.
        if errors:
            raise RuntimeError("Synchronizacja niekompletna; poprzednia baza pozostaje bez zmian:\n" + "\n".join(errors))
        if len(classes) < 10 or len(all_lessons) < 20:
            raise RuntimeError("Podejrzanie mały wynik importu; nie nadpisuję poprzedniej bazy.")

    print(f"Pobieram zmiany planu: {CHANGES_URL}")
    fresh_changes = parse_changes(fetch(CHANGES_URL))
    previous_week = existing_meta.get("week_start") == week_start.isoformat()
    previous_changes = existing_payload.get("changes", []) if previous_week else []
    changes = merge_week_changes(fresh_changes, previous_changes, week_start)
    print(f"Rozpoznano {len(fresh_changes)} wpisów; zachowano {len(changes)} zmian z bieżącego tygodnia.")

    meta = {
        **existing_meta,
        "source": BASE,
        "changes_source": CHANGES_URL,
        "updated_at": now.isoformat(),
        "week_start": week_start.isoformat(),
        "week_end": (week_start + timedelta(days=4)).isoformat(),
        "lesson_count": len(all_lessons),
        "changes_count": len(changes),
    }
    if not changes_only:
        meta["schedule_updated_at"] = now.isoformat()
        meta["class_count"] = len(classes)
        meta["classes"] = [{"class_name": c["class_name"], "label": c["label"]} for c in classes]

    payload = {"meta": meta, "lessons": all_lessons, "changes": changes}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=OUTPUT.parent, delete=False) as tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2)
        temp_name = tmp.name
    Path(temp_name).replace(OUTPUT)
    print(f"Zapisano {len(all_lessons)} lekcji z {len(classes)} oddziałów do {OUTPUT}")

if __name__ == "__main__":
    main(changes_only="--changes-only" in sys.argv[1:])
