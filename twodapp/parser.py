import re

MM_DIGITS = '၀၁၂၃၄၅၆၇၈၉'


def to_eng_digits(text):
    """Convert Myanmar digits (၀-၉) to English digits (0-9)."""
    return ''.join(str(MM_DIGITS.index(ch)) if ch in MM_DIGITS else ch for ch in text)


def gen_htek(d):
    """ထိပ် (Hteik) / Head - e.g. 5 -> 50,51,...,59"""
    return [f'{d}{i}' for i in range(10)]


def gen_nauk(d):
    """နောက် (Nauk) / Tail - e.g. 5 -> 05,15,...,95"""
    return [f'{i}{d}' for i in range(10)]


def gen_brake(d):
    """ဘရိတ် (Brake) - sum of digits % 10 equals d"""
    d = int(d)
    return [f'{i}{j}' for i in range(10) for j in range(10) if (i + j) % 10 == d]


def gen_puu():
    """ပူး (Puu) - doubles 00,11,...,99"""
    return [f'{i}{i}' for i in range(10)]


def gen_power():
    """Power - fixed pairs"""
    return ['05', '50', '16', '61', '27', '72', '38', '83', '49', '94']


def gen_natkhat():
    """နက္ခတ် (Natkhat) - fixed pairs"""
    return ['07', '70', '18', '81', '24', '42', '35', '53', '69', '96']


def gen_nyiko():
    """ညီကို (Nyi Ko) - consecutive pairs both directions"""
    res = []
    for i in range(9):
        res.append(f'{i}{i + 1}')
        res.append(f'{i + 1}{i}')
    res.append('09')
    res.append('90')
    return res


def gen_r(s):
    """R (Reverse) - the number plus its reverse"""
    if len(s) != 2:
        return [s]
    return [s, s[1] + s[0]]


def gen_hkway(chars_str, include_puu):
    """ခွေ (Hkway) - combinations of unique digits, optional doubles"""
    chars = list(dict.fromkeys(chars_str))
    res = []
    for i in range(len(chars)):
        for j in range(len(chars)):
            if i == j:
                if include_puu:
                    res.append(chars[i] + chars[i])
            else:
                res.append(chars[i] + chars[j])
    return res


def gen_kaut(s1, s2, is_reverse):
    """ကပ် (Kaut) - pair every digit of two numbers"""
    res = []
    for c1 in s1:
        for c2 in s2:
            res.append(c1 + c2)
            if is_reverse and c1 != c2:
                res.append(c2 + c1)
    return list(dict.fromkeys(res))


def _dedupe(items):
    return list(dict.fromkeys(items))


# Order is crucial: more specific patterns must come first.
PATTERNS = [
    {
        # Kaut: e.g. 2470 ကို 18 နဲ့ ကပ် r 1000 / 7980 ကို 12 r 1000
        'name': 'Kaut',
        'regex': re.compile(
            r'^(\d+)\s*(?:ကို|ko)\s*(\d+)\s*(?:နဲ့\s*ကပ်|နဲ့ကပ်|ကပ်|kap)?\s*(r|အာ)?\s*(\d+)$'
        ),
        'process': lambda m: gen_kaut(m.group(1), m.group(2), bool(m.group(3))),
    },
    {
        # Hkway Puu: e.g. 02468 kp 500
        'name': 'Hkway Puu',
        'regex': re.compile(r'^(\d{3,})\s*(kp|ခွေပူး)\s*(\d+)$'),
        'process': lambda m: gen_hkway(m.group(1), True),
    },
    {
        # Hkway: e.g. 02468 k 500
        'name': 'Hkway',
        'regex': re.compile(r'^(\d{3,})\s*(k|ခွေ|kway)\s*(\d+)$'),
        'process': lambda m: gen_hkway(m.group(1), False),
    },
    {
        # R (Reverse): e.g. 25 r 500
        'name': 'R (Reverse)',
        'regex': re.compile(r'^(\d{2,})\s*(r|အာ)\s*(\d+)$'),
        'process': lambda m: gen_r(m.group(1)),
    },
    {
        # Patshee: e.g. 5 p 500
        'name': 'Patshee',
        'regex': re.compile(r'^(\d)\s*(ပတ်|ပတ်သီး|ပါ|အပါ|p)\s*(\d+)$'),
        'process': lambda m: _dedupe(gen_htek(m.group(1)) + gen_nauk(m.group(1))),
    },
    {
        # Hteik: e.g. 5 t 500
        'name': 'Hteik',
        'regex': re.compile(r'^(\d)\s*(ထိပ်|t)\s*(\d+)$'),
        'process': lambda m: gen_htek(m.group(1)),
    },
    {
        # Nauk: e.g. 5 n 500
        'name': 'Nauk',
        'regex': re.compile(r'^(\d)\s*(နောက်|နောက်ပိတ်|န|n)\s*(\d+)$'),
        'process': lambda m: gen_nauk(m.group(1)),
    },
    {
        # Brake: e.g. 5 b 500
        'name': 'Brake',
        'regex': re.compile(r'^(\d)\s*(ဘရိတ်|bk|b)\s*(\d+)$'),
        'process': lambda m: gen_brake(m.group(1)),
    },
    {
        # Puu: e.g. ပူး 500
        'name': 'Puu',
        'regex': re.compile(r'^(အပူး|ပူး|pu)\s*(\d+)$'),
        'process': lambda m: gen_puu(),
    },
    {
        # Power: e.g. power 500
        'name': 'Power',
        'regex': re.compile(r'^(power|ပါဝါ|pw)\s*(\d+)$'),
        'process': lambda m: gen_power(),
    },
    {
        # Natkhat: e.g. nk 500
        'name': 'Natkhat',
        'regex': re.compile(r'^(နက္ခတ်|nk)\s*(\d+)$'),
        'process': lambda m: gen_natkhat(),
    },
    {
        # Nyi Ko: e.g. ညီကို 500
        'name': 'Nyi Ko',
        'regex': re.compile(r'^(ညီကို|ညီအကို|ညီအစ်ကို)\s*(\d+)$'),
        'process': lambda m: gen_nyiko(),
    },
    {
        # Direct: e.g. 25 500 or 25-500
        'name': 'Direct Bet',
        'regex': re.compile(r'^(\d{2})\s*(?:-|=|:)?\s*(\d+)$'),
        'process': lambda m: [m.group(1)],
    },
]


def parse_text(raw_text):
    """Parse Viber text into (parsed_results, errors).

    parsed_results: list of dicts with formula, original, count, amount, numbers
    errors: list of unparseable original lines
    """
    lines = re.split(r'[\n,]', raw_text)
    parsed = []
    errors = []

    for line in lines:
        original = line
        line = line.strip().lower()
        if not line:
            continue
        line = to_eng_digits(line)

        matched = False
        for pattern in PATTERNS:
            m = pattern['regex'].match(line)
            if m:
                try:
                    amount = int(m.group(len(m.groups())))
                except (ValueError, IndexError):
                    break
                if amount <= 0:
                    break
                numbers = pattern['process'](m)
                parsed.append({
                    'formula': pattern['name'],
                    'original': original,
                    'count': len(numbers),
                    'amount': amount,
                    'numbers': numbers,
                })
                matched = True
                break

        if not matched:
            errors.append(original)

    return parsed, errors
