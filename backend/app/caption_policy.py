from __future__ import annotations

import re
from pathlib import Path


CAPTION_PROMPT_PATH = Path(__file__).resolve().parents[2] / 'config' / 'detailed-caption-prompt.txt'
DEFAULT_DETAILED_CAPTION_PROMPT = CAPTION_PROMPT_PATH.read_text(encoding='utf-8').strip()
CAPTION_RETRY_INSTRUCTION = (
    'CORRECTION REQUIRED: Start the response with "EN:", write 60 to 120 factual English words, '
    'then insert exactly one blank line and write "ZH-CN:" followed by a complete natural Simplified '
    'Chinese rendering of the same visible facts. Include both paragraphs, remove speculative or '
    'sensitive wording, and return no other text.'
)
BILINGUAL_CAPTION_RE = re.compile(
    r'^\s*EN:\s*(?P<english>.+?)\s*\r?\n\s*\r?\n\s*ZH-CN:\s*(?P<chinese>.+?)\s*$',
    flags=re.DOTALL | re.IGNORECASE,
)
ENGLISH_POLICY_RE = re.compile(
    r'\b(seemingly|apparently|likely|probably|possibly|perhaps|maybe|suggests|man|woman|boy|girl|nude|naked|diaper|underwear|capturing|recording|photographing)\b'
    r'|looks like|no clothing|without clothing|taking (a |the )?(photo|picture|video)'
    r'|appear(s|ing)? to (capture|take|record|photograph|call|message)'
    r'|seem(s|ing)? to (capture|take|record|photograph|call|message)',
    flags=re.IGNORECASE,
)
CHINESE_POLICY_RE = re.compile(
    r'似乎|好像|可能|看起来|大概|或许|推测|拍摄|拍照|录像|录制'
    r'|男人|女人|男子|女子|男孩|女孩|男性|女性|裸体|赤裸|尿布|内衣|没穿衣服'
)
ENGLISH_PERSON_TERM_RE = re.compile(r'\b(women|woman|men|man|girls|girl|boys|boy)\b', re.IGNORECASE)
CHINESE_PERSON_TERM_RE = re.compile(r'男人|女人|男子|女子|男性|女性|男孩|女孩')
ENGLISH_PERSON_REPLACEMENTS = {
    'women': 'people',
    'woman': 'person',
    'men': 'people',
    'man': 'person',
    'girls': 'children',
    'girl': 'child',
    'boys': 'children',
    'boy': 'child',
}


def parse_bilingual_caption(text: str) -> tuple[str, str] | None:
    match = BILINGUAL_CAPTION_RE.fullmatch(str(text or ''))
    if not match:
        return None
    return match.group('english').strip(), match.group('chinese').strip()


def bilingual_caption_issues(
    text: str,
    min_english_words: int = 60,
    max_english_words: int = 120,
) -> list[str]:
    parts = parse_bilingual_caption(text)
    if parts is None:
        return ['format']

    english, chinese = parts
    issues: list[str] = []
    english_words = len(english.split())
    if not min_english_words <= english_words <= max_english_words:
        issues.append(f'english_words={english_words}')
    if not re.search(r'[\u4e00-\u9fff]', chinese):
        issues.append('chinese_script')
    if ENGLISH_POLICY_RE.search(english):
        issues.append('english_policy')
    if CHINESE_POLICY_RE.search(chinese):
        issues.append('chinese_policy')
    return issues


def build_caption_retry_prompt(prompt: str) -> str:
    return f'{str(prompt or "").strip()}\n\n{CAPTION_RETRY_INSTRUCTION}'.strip()


def neutralize_person_terms(text: str) -> str:
    def replace_english(match: re.Match[str]) -> str:
        source = match.group(0)
        replacement = ENGLISH_PERSON_REPLACEMENTS[source.lower()]
        return replacement.capitalize() if source[0].isupper() else replacement

    neutral = ENGLISH_PERSON_TERM_RE.sub(replace_english, str(text or ''))
    return CHINESE_PERSON_TERM_RE.sub(
        lambda match: '儿童' if match.group(0) in {'男孩', '女孩'} else '成人',
        neutral,
    )


def truncate_caption_text(text: str, word_limit: int) -> str:
    if word_limit <= 0:
        return text

    raw_text = str(text or '')
    bilingual = parse_bilingual_caption(raw_text)
    if bilingual:
        return f'EN: {bilingual[0]}\n\nZH-CN: {bilingual[1]}'

    words = [word for word in raw_text.split() if word]
    if len(words) <= word_limit:
        return raw_text

    sentence_end_re = re.compile(r'[.!?。！？][\'\")\]]*$')

    def _join(count: int) -> str:
        return ' '.join(words[:max(1, count)]).strip()

    for index in range(word_limit, 0, -1):
        if sentence_end_re.search(words[index - 1]):
            return _join(index)

    forward_limit = min(len(words), word_limit + 24)
    for index in range(word_limit + 1, forward_limit + 1):
        if sentence_end_re.search(words[index - 1]):
            return _join(index)

    return _join(word_limit)
