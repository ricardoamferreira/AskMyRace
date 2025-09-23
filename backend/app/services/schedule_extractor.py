from __future__ import annotations

import io
import re
from collections import OrderedDict, defaultdict
from typing import Iterable, List, Sequence, Tuple

from backend.app.services.document_registry import ScheduleDay, ScheduleItem
from backend.app.services.pdf_loader import PageChunk

try:
    import pdfplumber  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pdfplumber = None


_SCHEDULE_SECTION_KEYWORDS = (
    "schedule",
    "time activity",
)
_BLOCKLISTED_SECTION_PHRASES = (
    "location",
    "broadcast",
    "pro race",
    "cut-off",
)
_DAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]
_MONTH_NAMES = {
    "JANUARY",
    "FEBRUARY",
    "MARCH",
    "APRIL",
    "MAY",
    "JUNE",
    "JULY",
    "AUGUST",
    "SEPTEMBER",
    "OCTOBER",
    "NOVEMBER",
    "DECEMBER",
}
_HEADER_STRINGS = {
    "TIME ACTIVITY",
    "TIME ACTIVITY LOCATION",
    "EVENT SCHEDULE",
    "RACE START TIMES",
    "PRIZE-GIVING TIMES",
}
_TIME_PATTERN = re.compile(
    r"^(?P<time>\d{1,2}:\d{2}(?:\s*[\u2013\u2014-]\s*\d{1,2}:\d{2})?(?:\s*(?:AM|PM))?)",
    re.IGNORECASE,
)
_ORDINAL_PATTERN = re.compile(r"^\d{1,2}(?:ST|ND|RD|TH)$", re.IGNORECASE)
_DAY_LINE_PATTERN = re.compile(
    r"^(?P<day>Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(?P<date>.+?)$",
    re.IGNORECASE,
)
_TIME_TOKEN_PATTERN = re.compile(
    r"^(?:\d{1,2}:\d{2}(?:[\-\u2013\u2014]\d{1,2}:\d{2})?|[\-\u2013\u2014]|to)$",
    re.IGNORECASE,
)




def extract_schedule(file_bytes: bytes, chunks: Sequence[PageChunk]) -> List[ScheduleDay]:
    pages = sorted({chunk.page for chunk in chunks if _looks_like_schedule_section(chunk.section)})
    if not pages:
        return []

    schedule: List[ScheduleDay] = []

    if pdfplumber is not None:
        layout_schedule = _extract_with_layout(file_bytes, pages)
        if layout_schedule:
            schedule = layout_schedule

    if not schedule:
        schedule = _extract_from_text(chunks)

    return schedule


def _extract_with_layout(file_bytes: bytes, pages: Sequence[int]) -> List[ScheduleDay]:
    try:
        pdf = pdfplumber.open(io.BytesIO(file_bytes))
    except Exception:
        return []

    try:
        collected: OrderedDict[str, ScheduleDay] = OrderedDict()
        for page_number in pages:
            if page_number - 1 < 0 or page_number - 1 >= len(pdf.pages):
                continue
            page = pdf.pages[page_number - 1]
            days = _parse_schedule_page(page)
            for day in days:
                existing = collected.get(day.title)
                if existing:
                    seen = {(item.time, item.activity) for item in existing.items}
                    for item in day.items:
                        if (item.time, item.activity) not in seen:
                            existing.items.append(item)
                else:
                    collected[day.title] = day
        return list(collected.values())
    finally:
        pdf.close()


def _parse_schedule_page(page: "pdfplumber.page.Page") -> List[ScheduleDay]:  # type: ignore[name-defined]
    words = page.extract_words(keep_blank_chars=False, use_text_flow=True)
    if not words:
        return []

    lines = _group_words_by_line(words)
    day_rows = _detect_day_rows(lines)
    if not day_rows:
        return []

    schedule: List[ScheduleDay] = []
    for index, (title, start_top) in enumerate(day_rows):
        end_top = day_rows[index + 1][1] if index + 1 < len(day_rows) else float("inf")
        items = _collect_items_for_range(lines, start_top, end_top)
        if not items:
            continue
        day = ScheduleDay(title=title)
        day.items.extend(items)
        schedule.append(day)
    return schedule


def _group_words_by_line(words: Sequence[dict]) -> List[Tuple[float, List[dict]]]:
    grouped: defaultdict[float, List[dict]] = defaultdict(list)
    for word in words:
        key = round(float(word["top"]), 1)
        grouped[key].append(word)
    lines: List[Tuple[float, List[dict]]] = []
    for key, items in grouped.items():
        line_top = min(float(item["top"]) for item in items)
        sorted_items = sorted(items, key=lambda item: float(item["x0"]))
        lines.append((line_top, sorted_items))
    lines.sort(key=lambda entry: entry[0])
    return lines


def _detect_day_rows(lines: Sequence[Tuple[float, List[dict]]]) -> List[Tuple[str, float]]:
    day_rows: List[Tuple[str, float]] = []
    seen_titles: set[str] = set()
    for top, words in lines:
        text = " ".join(word["text"] for word in words).strip()
        match = _DAY_LINE_PATTERN.match(text)
        if not match:
            continue
        day = match.group("day").title()
        remainder = match.group("date").strip()
        normalized = _normalize_title(f"{day} {remainder}")
        if not normalized or normalized in seen_titles:
            continue
        seen_titles.add(normalized)
        day_rows.append((normalized, top))
    return day_rows


def _collect_items_for_range(
    lines: Sequence[Tuple[float, List[dict]]],
    start_top: float,
    end_top: float,
) -> List[ScheduleItem]:
    entries = _build_day_entries(lines, start_top, end_top)
    if not entries:
        return []
    items: List[ScheduleItem] = []
    seen: set[Tuple[str, str]] = set()
    used_indices: set[int] = set()

    for idx, entry in enumerate(entries):
        if idx in used_indices:
            continue
        if not _looks_like_time_word(entry.text):
            continue
        group_indices = _expand_time_group(entries, idx)
        used_indices.update(group_indices)
        group_entries = [entries[i] for i in group_indices]
        time_text = _normalize_time_tokens([item.text for item in group_entries])
        desc_texts, desc_indices = _collect_description(entries, group_entries, used_indices)
        if not desc_texts:
            continue
        used_indices.update(desc_indices)
        activity = _clean_activity_text(" ".join(desc_texts))
        if not activity:
            continue
        key = (time_text, activity.lower())
        if key in seen:
            continue
        seen.add(key)
        items.append(ScheduleItem(time=time_text, activity=activity))

    return items


def _build_day_entries(
    lines: Sequence[Tuple[float, List[dict]]],
    start_top: float,
    end_top: float,
) -> List["_Entry"]:
    words: List[dict] = []
    for top, line_words in lines:
        if top <= start_top or top >= end_top:
            continue
        words.extend(line_words)
    if not words:
        return []
    sorted_words = sorted(words, key=lambda word: (float(word["top"]), float(word["x0"])))
    entries: List[_Entry] = []
    counter = 0
    for word in sorted_words:
        text = str(word.get("text", "")).strip()
        if not text:
            continue
        entries.append(
            _Entry(
                index=counter,
                text=text,
                top=float(word["top"]),
                x0=float(word["x0"]),
                x1=float(word["x1"]),
            )
        )
        counter += 1
    return entries


class _Entry:

    def __init__(self, index: int, text: str, top: float, x0: float, x1: float) -> None:
        self.index = index
        self.text = text
        self.top = top
        self.x0 = x0
        self.x1 = x1


def _looks_like_time_word(text: str) -> bool:
    return bool(re.match(r"^\d{1,2}:\d{2}(?:[\-\u2013\u2014]\d{1,2}:\d{2})?$", text))


def _expand_time_group(entries: Sequence[_Entry], start_index: int) -> List[int]:
    group = [start_index]
    base = entries[start_index]
    idx = start_index + 1
    while idx < len(entries):
        candidate = entries[idx]
        if abs(candidate.top - base.top) > 1.2:
            break
        if not _is_time_token(candidate.text):
            break
        group.append(idx)
        idx += 1
    return group


def _collect_description(
    entries: Sequence[_Entry],
    time_group: Sequence[_Entry],
    used_indices: set[int],
) -> Tuple[List[str], List[int]]:
    time_top = sum(item.top for item in time_group) / len(time_group)
    min_top = time_top - 12
    max_top = time_top + 16
    min_x = max(item.x1 for item in time_group) + 4

    collected: List[_Entry] = []
    collected_indices: List[int] = []
    for entry in entries:
        if entry.index in used_indices:
            continue
        if entry.top < min_top or entry.top > max_top:
            continue
        if entry.x0 < min_x:
            continue
        collected.append(entry)
        collected_indices.append(entry.index)

    if not collected:
        return [], []

    collected.sort(key=lambda item: (item.top, item.x0))
    texts = [item.text for item in collected]
    return texts, collected_indices


def _clean_activity_text(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    if not cleaned:
        return ""
    # remove trailing footnotes or page artefacts
    cleaned = re.split(r"\s+\*\s+", cleaned)[0]
    cleaned = re.sub(r"\s*\d+\s+t100triathlon\.com$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*your wave start time.*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*start times will also be listed.*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+\d+$", "", cleaned)
    cleaned = cleaned.strip(" -")
    return cleaned.strip()


def _extract_from_text(chunks: Sequence[PageChunk]) -> List[ScheduleDay]:
    sections: OrderedDict[str, List[Tuple[str, str]]] = OrderedDict()
    seen: set[Tuple[str, str, str]] = set()
    current_title: str | None = None

    for chunk in chunks:
        if not _looks_like_schedule_section(chunk.section):
            continue
        text = chunk.text
        if not text:
            continue
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or _should_skip_line(line):
                continue
            day_label = _parse_day_label(line)
            if day_label:
                current_title = day_label
                sections.setdefault(day_label, [])
                continue
            parsed = _parse_time_and_activity(line)
            if not parsed or current_title is None:
                continue
            time_value, activity = parsed
            key = (current_title.lower(), time_value, activity.lower())
            if key in seen:
                continue
            seen.add(key)
            sections[current_title].append((time_value, activity))

    schedule: List[ScheduleDay] = []
    for title, entries in sections.items():
        if not entries:
            continue
        day = ScheduleDay(title=title)
        for time_value, activity in entries:
            day.items.append(ScheduleItem(time=time_value, activity=activity))
        schedule.append(day)
    return schedule


def _looks_like_schedule_section(section_title: str) -> bool:
    if not section_title:
        return False
    lowered = section_title.lower()
    squashed = lowered.replace(" ", "")
    if any(phrase in lowered or phrase in squashed for phrase in _BLOCKLISTED_SECTION_PHRASES):
        return False
    return any(keyword in lowered for keyword in _SCHEDULE_SECTION_KEYWORDS)


def _should_skip_line(line: str) -> bool:
    cleaned = re.sub(r"\s+", " ", line).strip()
    if not cleaned:
        return True
    if cleaned.startswith("*"):
        return True
    lower = cleaned.lower()
    if "t100triathlon.com" in lower:
        return True
    upper = cleaned.upper()
    if upper.startswith("PAGE "):
        return True
    if upper in _HEADER_STRINGS:
        return True
    return False


def _parse_day_label(line: str) -> str | None:
    tokens = re.findall(r"[A-Za-z0-9]+", line)
    if not tokens:
        return None
    upper_tokens = [token.upper() for token in tokens]
    for index in range(1, min(len(tokens), 4)):
        candidate = "".join(upper_tokens[:index])
        for day_name in _DAY_NAMES:
            if candidate == day_name.upper():
                remainder = tokens[index:]
                result = _assemble_day_label(day_name, remainder)
                if result:
                    return result
    return None


def _assemble_day_label(day_name: str, remainder_tokens: Iterable[str]) -> str | None:
    parts = [day_name]
    has_detail = False
    for token in remainder_tokens:
        upper = token.upper()
        if token.isdigit() or _ORDINAL_PATTERN.match(token):
            parts.append(token)
            has_detail = True
            continue
        if upper in _MONTH_NAMES:
            parts.append(token.title())
            has_detail = True
            continue
        break
    if not has_detail:
        return None
    return _normalize_title(" ".join(parts))


def _parse_time_and_activity(line: str) -> Tuple[str, str] | None:
    match = _TIME_PATTERN.match(line)
    if not match:
        return None
    time_value_raw = match.group("time")
    time_value = re.sub(r"\s*[\u2013\u2014-]\s*", " - ", time_value_raw).upper()
    remainder = line[match.end():].strip().strip("-\u2013\u2014")
    if not remainder:
        return None
    remainder = remainder.replace("**", "").replace("*", "").strip()
    remainder = re.sub(r"(EVENT|PRO|RACE)\s+SCHEDULE.*$", "", remainder, flags=re.IGNORECASE)
    remainder = re.sub(r"\s+", " ", remainder).strip()
    if not remainder:
        return None
    if _parse_day_label(remainder):
        return None
    remainder = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", remainder)
    return time_value, remainder


def _normalize_title(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned.title()


def _is_time_token(token: str) -> bool:
    stripped = token.strip()
    return bool(_TIME_TOKEN_PATTERN.match(stripped) or re.match(r"^-?\d{1,2}:\d{2}$", stripped))


def _normalize_time_tokens(tokens: Sequence[str]) -> str:
    joined = " ".join(tokens)
    joined = re.sub(r"\s*[\u2013\u2014-]\s*", " - ", joined)
    joined = re.sub(r"\s+", " ", joined)
    return joined.strip().upper()


def _normalize_description(tokens: Sequence[str]) -> str:
    text = " ".join(tokens)
    return re.sub(r"\s+", " ", text).strip()
