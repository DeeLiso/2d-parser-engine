import functools
import json
import urllib.request
from zoneinfo import ZoneInfo

from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from .models import GameState, OperationLog
from .parser import parse_text

MMT = ZoneInfo('Asia/Yangon')


def robots_txt(request):
    return HttpResponse('User-agent: *\nDisallow: /\n', content_type='text/plain')


def api_login_required(fn):
    @functools.wraps(fn)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'ok': False, 'error': 'Not authenticated'}, status=403)
        return fn(request, *args, **kwargs)
    return wrapper


def logout_view(request):
    logout(request)
    return redirect('login')


def _serialize_log(log):
    return {
        'id': log.pk,
        'formula': log.formula,
        'original': log.original,
        'numbers': log.numbers,
        'count': log.count,
        'amount': log.amount,
        'is_error': log.is_error,
        'is_canceled': log.is_canceled,
        'bettor_name': log.bettor_name,
        'bettor_date': log.bettor_date,
        'time': log.created_at.astimezone(MMT).strftime('%Y-%m-%d %H:%M:%S'),
    }


def over_limit_items(state):
    bettors_by_num = {}
    for name, nums in OperationLog.objects.exclude(bettor_name='').values_list('bettor_name', 'numbers'):
        for n in nums or []:
            bettors_by_num.setdefault(n, set()).add(name)
    items = []
    for i, amt in enumerate(state.ledger):
        num = f'{i:02d}'
        limit = state.specific_limits.get(num) or state.global_limit
        if limit and amt >= limit:
            items.append({
                'num': num, 'amount': amt, 'limit': limit, 'over': amt - limit,
                'bettors': sorted(bettors_by_num.get(num, set()))[:3],
            })
    return items


@login_required
def records_page(request):
    state = GameState.get_state()
    records = [_serialize_log(l) for l in OperationLog.objects.order_by('-id')[:1000]]
    return render(request, 'twodapp/records.html', {
        'records_json': json.dumps(records),
        'count': len(records),
        'over_limits_json': json.dumps(over_limit_items(state)),
    })


@login_required
def limit_page(request):
    state = GameState.get_state()
    over = over_limit_items(state)
    over_map = {o['num']: o for o in over}
    logs = []
    for l in OperationLog.objects.order_by('-id')[:2000]:
        if l.is_error:
            continue
        hit = [n for n in (l.numbers or []) if n in over_map]
        if not hit:
            continue
        logs.append({
            'id': l.pk,
            'formula': l.formula,
            'original': l.original,
            'numbers': l.numbers or [],
            'amount': l.amount,
            'bettor_name': l.bettor_name,
            'time': l.created_at.astimezone(MMT).strftime('%Y-%m-%d %H:%M:%S'),
            'over_nums': hit,
            'over_detail': [over_map[n] for n in hit],
        })
    return render(request, 'twodapp/limit.html', {
        'over_limits_json': json.dumps(over),
        'logs_json': json.dumps(logs),
        'count': len(logs),
    })


@login_required
def ledger_page(request):
    state = GameState.get_state()
    return render(request, 'twodapp/ledger.html', {
        'ledger_json': json.dumps(state.ledger),
        'specific_limits_json': json.dumps(state.specific_limits),
        'global_limit': state.global_limit,
        'total_amount': state.total_amount,
        'valid_lines': state.valid_lines,
    })


def state_payload(state):
    over = 0
    for i, amt in enumerate(state.ledger):
        num = f'{i:02d}'
        limit = state.specific_limits.get(num) or state.global_limit
        if amt >= limit:
            over += 1
    return {
        'ledger': state.ledger,
        'global_limit': state.global_limit,
        'specific_limits': state.specific_limits,
        'total_amount': state.total_amount,
        'valid_lines': state.valid_lines,
        'over_limit': over,
    }


@login_required
def index(request):
    state = GameState.get_state()
    records = [_serialize_log(l) for l in OperationLog.objects.order_by('-id')[:200]]
    return render(request, 'twodapp/index.html', {
        'ledger_json': json.dumps(state.ledger),
        'specific_limits_json': json.dumps(state.specific_limits),
        'global_limit': state.global_limit,
        'total_amount': state.total_amount,
        'valid_lines': state.valid_lines,
        'bettor_name': state.bettor_name,
        'bettor_date': state.bettor_date,
        'logs_json': json.dumps(records),
        'over_limits_json': json.dumps(over_limit_items(state)),
    })


@require_GET
@api_login_required
def api_live(request):
    """Proxy the Thai Stock 2D live API to avoid CORS issues."""
    try:
        req = urllib.request.Request(
            'https://api.thaistock2d.com/live',
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        live = data.get('live', {})
        result = data.get('result', [])
        return JsonResponse({
            'ok': True,
            'result': live.get('twod', '--'),
            'set': live.get('set', '--'),
            'value': live.get('value', '--'),
            'time': live.get('time', ''),
            'today_results': [
                {
                    'time': r.get('open_time', ''),
                    'result': r.get('twod', '--'),
                    'set': r.get('set', '--'),
                    'value': r.get('value', '--'),
                }
                for r in result
            ],
            'holiday': data.get('holiday', {}),
        })
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)})


@require_POST
@api_login_required
def api_parse(request):
    text = request.POST.get('text', '')
    action = request.POST.get('action', 'add')  # 'add' or 'delete'
    bettor_name = request.POST.get('bettor_name', '').strip()
    bettor_date = request.POST.get('bettor_date', '').strip()
    state = GameState.get_state()
    parsed, errors = parse_text(text)
    log_entries = []

    ledger = list(state.ledger)
    for r in parsed:
        for num in r['numbers']:
            idx = int(num)
            if 0 <= idx < 100:
                if action == 'delete':
                    ledger[idx] = max(0, ledger[idx] - r['amount'])
                    state.total_amount = max(0, state.total_amount - r['amount'])
                else:
                    ledger[idx] += r['amount']
                    state.total_amount += r['amount']
        state.valid_lines += 1
        log = OperationLog.objects.create(
            formula=r['formula'], original=r['original'],
            numbers=r['numbers'], count=r['count'], amount=r['amount'],
            bettor_name=bettor_name, bettor_date=bettor_date,
        )
        log_entries.append(_serialize_log(log))

    for err in errors:
        log = OperationLog.objects.create(original=err, is_error=True)
        log_entries.append(_serialize_log(log))

    state.ledger = ledger
    state.save()
    return JsonResponse({'ok': True, 'logs': log_entries, **state_payload(state)})


@require_POST
@api_login_required
def api_set_global_limit(request):
    try:
        val = int(request.POST.get('limit', ''))
    except ValueError:
        val = 0
    if val > 0:
        state = GameState.get_state()
        state.global_limit = val
        state.save()
        return JsonResponse({'ok': True, **state_payload(state)})
    return JsonResponse({'ok': False, 'error': 'Invalid limit'})


@require_POST
@api_login_required
def api_delete_logs(request):
    ids_raw = request.POST.get('ids', '')
    state = GameState.get_state()
    ledger = list(state.ledger)
    try:
        ids = [int(x) for x in ids_raw.split(',') if x.strip().isdigit()]
    except ValueError:
        ids = []
    if not ids:
        return JsonResponse({'ok': False, 'error': 'Invalid ids'})
    for log in OperationLog.objects.filter(pk__in=ids):
        for num in log.numbers or []:
            try:
                idx = int(num)
            except (ValueError, TypeError):
                continue
            if 0 <= idx < 100:
                ledger[idx] = max(0, ledger[idx] - log.amount)
                state.total_amount = max(0, state.total_amount - log.amount)
    state.ledger = ledger
    state.valid_lines = max(0, state.valid_lines - OperationLog.objects.filter(pk__in=ids, is_error=False).count())
    state.save()
    OperationLog.objects.filter(pk__in=ids).delete()
    return JsonResponse({'ok': True, **state_payload(state)})


@require_POST
@api_login_required
def api_toggle_cancel(request):
    """Cancel or restore one or more records, adjusting the ledger accordingly.
    Expects 'ids' (comma-separated) and 'canceled' (true/false).
    """
    ids_raw = request.POST.get('ids', '')
    canceled = request.POST.get('canceled', 'true').lower() == 'true'
    ids = [int(x) for x in ids_raw.split(',') if x.strip().isdigit()]
    if not ids:
        return JsonResponse({'ok': False, 'error': 'Invalid ids'})

    state = GameState.get_state()
    ledger = list(state.ledger)
    for log in OperationLog.objects.filter(pk__in=ids):
        if canceled == log.is_canceled:
            continue
        sign = -1 if canceled else 1
        for num in log.numbers or []:
            try:
                idx = int(num)
            except (ValueError, TypeError):
                continue
            if 0 <= idx < 100:
                ledger[idx] = max(0, ledger[idx] + sign * log.amount)
                state.total_amount = max(0, state.total_amount + sign * log.amount)
        log.is_canceled = canceled
        log.save()
    state.ledger = ledger
    state.save()
    return JsonResponse({'ok': True, **state_payload(state)})


@require_POST
@api_login_required
def api_edit_logs(request):
    """Edit amounts for multiple records at once.
    Expects 'items' = JSON list of {"id": <int>, "amount": <int>}.
    """
    import json as _json
    try:
        items = _json.loads(request.POST.get('items', '[]'))
    except (ValueError, TypeError):
        items = []
    if not items:
        return JsonResponse({'ok': False, 'error': 'No items'})

    state = GameState.get_state()
    ledger = list(state.ledger)
    updates = []
    for it in items:
        try:
            log_id = int(it.get('id'))
            new_amount = int(it.get('amount'))
        except (ValueError, TypeError):
            continue
        if new_amount <= 0:
            continue
        updates.append((log_id, new_amount))

    logs = OperationLog.objects.filter(pk__in=[u[0] for u in updates])
    for log in logs:
        new_amount = dict(updates)[log.pk]
        diff = new_amount - log.amount
        if diff == 0:
            continue
        for num in log.numbers or []:
            try:
                idx = int(num)
            except (ValueError, TypeError):
                continue
            if 0 <= idx < 100:
                ledger[idx] = max(0, ledger[idx] + diff)
                state.total_amount = max(0, state.total_amount + diff)
        log.amount = new_amount
        log.save()

    state.ledger = ledger
    state.save()
    return JsonResponse({'ok': True, **state_payload(state)})


@require_POST
@api_login_required
def api_set_specific_limit(request):
    num = request.POST.get('num', '').strip()
    num = num.zfill(2) if num.isdigit() else ''
    try:
        val = int(request.POST.get('limit', ''))
    except ValueError:
        val = 0

    state = GameState.get_state()
    if num and len(num) == 2 and 0 <= int(num) < 100:
        limits = dict(state.specific_limits)
        if val > 0:
            limits[num] = val
        else:
            limits.pop(num, None)
        state.specific_limits = limits
        state.save()
        return JsonResponse({'ok': True, **state_payload(state)})
    return JsonResponse({'ok': False, 'error': 'Invalid number'})


@require_POST
@api_login_required
def api_delete_specific_limit(request):
    num = request.POST.get('num', '').strip()
    state = GameState.get_state()
    limits = dict(state.specific_limits)
    limits.pop(num, None)
    state.specific_limits = limits
    state.save()
    return JsonResponse({'ok': True, **state_payload(state)})


@require_POST
@api_login_required
def api_save_meta(request):
    name = request.POST.get('name', '').strip()
    date = request.POST.get('date', '').strip()
    state = GameState.get_state()
    state.bettor_name = name
    state.bettor_date = date
    state.save()
    return JsonResponse({'ok': True, 'bettor_name': name, 'bettor_date': date})


@require_POST
@api_login_required
def api_clear_all(request):
    state = GameState.get_state()
    state.ledger = [0] * 100
    state.specific_limits = {}
    state.total_amount = 0
    state.valid_lines = 0
    state.bettor_name = ''
    state.bettor_date = ''
    state.save()
    OperationLog.objects.all().delete()
    return JsonResponse({'ok': True, **state_payload(state)})
