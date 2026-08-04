import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .models import GameState, OperationLog
from .parser import parse_text


def _serialize_log(log):
    return {
        'id': log.pk,
        'formula': log.formula,
        'original': log.original,
        'numbers': log.numbers,
        'count': log.count,
        'amount': log.amount,
        'is_error': log.is_error,
        'bettor_name': log.bettor_name,
        'bettor_date': log.bettor_date,
        'time': log.created_at.astimezone().strftime('%Y-%m-%d %H:%M:%S'),
    }


def records_page(request):
    records = [_serialize_log(l) for l in OperationLog.objects.order_by('-id')[:1000]]
    return render(request, 'twodapp/records.html', {
        'records_json': json.dumps(records),
        'count': len(records),
    })


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
    })


@require_POST
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
def api_delete_specific_limit(request):
    num = request.POST.get('num', '').strip()
    state = GameState.get_state()
    limits = dict(state.specific_limits)
    limits.pop(num, None)
    state.specific_limits = limits
    state.save()
    return JsonResponse({'ok': True, **state_payload(state)})


@require_POST
def api_save_meta(request):
    name = request.POST.get('name', '').strip()
    date = request.POST.get('date', '').strip()
    state = GameState.get_state()
    state.bettor_name = name
    state.bettor_date = date
    state.save()
    return JsonResponse({'ok': True, 'bettor_name': name, 'bettor_date': date})


@require_POST
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
