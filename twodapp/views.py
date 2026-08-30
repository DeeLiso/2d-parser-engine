import functools
import json
import urllib.request
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import GameState, OperationLog, BettorAccount, ChatMessage, ChatPresence, ChatReaction, PlayerNotification
from .parser import parse_text

MMT = ZoneInfo('Asia/Yangon')


def robots_txt(request):
    return HttpResponse('User-agent: *\nDisallow: /\n', content_type='text/plain')


def api_login_required(fn):
    @functools.wraps(fn)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated and not request.session.get('bettor_account_id'):
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
        'bettor_username': log.bettor_username,
        'status': log.status,
        'group_id': log.group_id,
        'time': log.created_at.astimezone(MMT).strftime('%Y-%m-%d %H:%M:%S'),
    }


def over_limit_items(state):
    bettors_by_num = {}
    for name, nums in OperationLog.objects.filter(status='approved').exclude(bettor_name='').values_list('bettor_name', 'numbers'):
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
    records = [_serialize_log(l) for l in OperationLog.objects.filter(status='approved').order_by('-id')[:1000]]
    return render(request, 'twodapp/records.html', {
        'records_json': json.dumps(records),
        'count': len(records),
        'over_limits_json': json.dumps(over_limit_items(state)),
    })


@api_login_required
def bettor_records_page(request):
    bettor_username = request.session.get('bettor_username', '')
    state = GameState.get_state()
    logs = OperationLog.objects.filter(bettor_username=bettor_username).order_by('-id')[:500] if bettor_username else []
    records = [_serialize_log(l) for l in logs]
    return render(request, 'twodapp/bettor_records.html', {
        'records_json': json.dumps(records),
        'count': len(records),
        'bettor_name': bettor_username,
    })


@login_required
def limit_page(request):
    state = GameState.get_state()
    over = over_limit_items(state)
    over_map = {o['num']: o for o in over}
    logs = []
    for l in OperationLog.objects.filter(status='approved').order_by('-id')[:2000]:
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
def home_page(request):
    return render(request, 'twodapp/home.html')


def index(request):
    state = GameState.get_state()
    records = [_serialize_log(l) for l in OperationLog.objects.filter(status='approved').order_by('-id')[:200]]
    user_type = request.GET.get('type', 'dealer')
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
        'user_type': user_type,
        'bettor_username': request.session.get('bettor_username', ''),
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
    bettor_username = request.session.get('bettor_username', '')
    is_player = bool(bettor_username)
    state = GameState.get_state()
    parsed, errors = parse_text(text)
    log_entries = []

    # Player submissions enter a pending queue and do NOT update the ledger
    # until the admin approves them. Admin/dealer entries apply immediately.
    if is_player:
        group_id = uuid4().hex
        for r in parsed:
            log = OperationLog.objects.create(
                formula=r['formula'], original=r['original'],
                numbers=r['numbers'], count=r['count'], amount=r['amount'],
                bettor_name=bettor_name, bettor_date=bettor_date,
                bettor_username=bettor_username,
                status='pending', group_id=group_id,
            )
            log_entries.append(_serialize_log(log))
        for err in errors:
            log = OperationLog.objects.create(original=err, is_error=True)
            log_entries.append(_serialize_log(log))
        return JsonResponse({
            'ok': True,
            'logs': log_entries,
            'needs_approval': True,
            **state_payload(state),
        })

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
            bettor_username=bettor_username,
            status='approved',
        )
        log_entries.append(_serialize_log(log))

    for err in errors:
        log = OperationLog.objects.create(original=err, is_error=True)
        log_entries.append(_serialize_log(log))

    state.ledger = ledger
    state.save()
    return JsonResponse({'ok': True, 'logs': log_entries, 'needs_approval': False, **state_payload(state)})


def _group_pending():
    """Return a list of pending submissions (grouped by group_id), newest first."""
    pending = OperationLog.objects.filter(status='pending').order_by('-id')
    groups = {}
    order = []
    for log in pending:
        if log.group_id not in groups:
            groups[log.group_id] = {'lines': [], 'total': 0, 'count': 0, 'time': ''}
            order.append(log.group_id)
        g = groups[log.group_id]
        g['lines'].append(_serialize_log(log))
        g['count'] += 1
        try:
            g['total'] += (log.count or 1) * (log.amount or 0)
        except (TypeError, ValueError):
            pass
        if not g['time']:
            g['time'] = _serialize_log(log)['time']
    result = []
    for gid in order:
        g = groups[gid]
        result.append({
            'group_id': gid,
            'bettor_name': g['lines'][0].get('bettor_name') or g['lines'][0].get('bettor_username') or '',
            'bettor_username': g['lines'][0].get('bettor_username', ''),
            'time': g['time'],
            'lines': g['lines'],
            'total': g['total'],
            'count': g['count'],
        })
    return result


@require_GET
@login_required
def api_pending_submissions(request):
    """Admin: list pending player submissions and whether any await approval."""
    pending = _group_pending()
    return JsonResponse({'ok': True, 'pending': pending})


def _apply_group(state, logs, subtract=False):
    """Apply a group's ledger effect. Returns number of valid lines applied."""
    ledger = list(state.ledger)
    lines = 0
    for log in logs:
        if log.is_error:
            continue
        lines += 1
        for num in log.numbers or []:
            try:
                idx = int(num)
            except (ValueError, TypeError):
                continue
            if 0 <= idx < 100:
                amt = log.amount or 0
                if subtract:
                    ledger[idx] = max(0, ledger[idx] - amt)
                    state.total_amount = max(0, state.total_amount - amt)
                else:
                    ledger[idx] += amt
                    state.total_amount += amt
    state.ledger = ledger
    state.valid_lines = max(0, state.valid_lines + lines)
    state.save()
    return lines


@require_POST
@login_required
def api_approve_submission(request):
    data = json.loads(request.body)
    group_id = data.get('group_id', '')
    logs = list(OperationLog.objects.filter(group_id=group_id, status='pending'))
    if not logs:
        return JsonResponse({'ok': False, 'error': 'Pending submission not found'})
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False, 'error': 'Owner only'})
    state = GameState.get_state()
    _apply_group(state, logs, subtract=False)
    OperationLog.objects.filter(group_id=group_id, status='pending').update(status='approved')
    notif_user = logs[0].bettor_username or ''
    if notif_user:
        PlayerNotification.objects.create(
            bettor_username=notif_user, kind='approved', group_id=group_id,
            message='admin မှ စာရင်းကို လက်ခံရရှိပါသည်',
        )
    return JsonResponse({'ok': True, **state_payload(state)})


@require_POST
@login_required
def api_reject_submission(request):
    data = json.loads(request.body)
    group_id = data.get('group_id', '')
    logs = list(OperationLog.objects.filter(group_id=group_id, status='pending'))
    if not logs:
        return JsonResponse({'ok': False, 'error': 'Pending submission not found'})
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False, 'error': 'Owner only'})
    OperationLog.objects.filter(group_id=group_id, status='pending').update(status='rejected')
    notif_user = logs[0].bettor_username or ''
    if notif_user:
        PlayerNotification.objects.create(
            bettor_username=notif_user, kind='rejected', group_id=group_id,
            message='admin မှ စာရင်းကို ပယ်ချထားပါသည်',
        )
    return JsonResponse({'ok': True})


@require_GET
@api_login_required
def api_player_notifications(request):
    """Player: return new approve/reject notifications since the given id."""
    after = request.GET.get('after', '0') or '0'
    try:
        after = int(after)
    except (ValueError, TypeError):
        after = 0
    bettor_username = request.session.get('bettor_username', '')
    notifs = list(PlayerNotification.objects.filter(
        id__gt=after, bettor_username=bettor_username).order_by('id')[:50])
    data = [
        {'id': n.id, 'kind': n.kind, 'message': n.message, 'group_id': n.group_id,
         'time': n.created_at.astimezone(MMT).strftime('%H:%M')}
        for n in notifs
    ]
    return JsonResponse({'ok': True, 'notifications': data})


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


@login_required
@require_POST
def api_create_bettor(request):
    data = json.loads(request.body)
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    phone = (data.get('phone') or '').strip()
    balance = int(data.get('balance') or 0)
    hot_limits = data.get('hot_limits') or {}
    multiplier = int(data.get('multiplier') or 10)
    if multiplier < 1:
        multiplier = 10

    if not username or not password:
        return JsonResponse({'ok': False, 'error': 'Username + password required'})
    if BettorAccount.objects.filter(username=username).exists():
        return JsonResponse({'ok': False, 'error': f'"{username}" already exists'})

    acc = BettorAccount(username=username, phone=phone, balance=balance, hot_limits=hot_limits, multiplier=multiplier)
    acc.set_password(password)
    acc.save()
    return JsonResponse({'ok': True, 'account': acc.to_dict()})


@login_required
@require_GET
def api_list_bettors(request):
    accs = list(BettorAccount.objects.all().order_by('-id').values(
        'id', 'username', 'phone', 'balance', 'hot_limits', 'multiplier', 'is_active',
        'last_user_agent', 'last_ip', 'last_seen'
    ))
    for a in accs:
        if a.get('last_seen'):
            a['last_seen'] = a['last_seen'].strftime('%Y-%m-%d %H:%M')
    return JsonResponse({'ok': True, 'accounts': accs})


@login_required
@require_POST
def api_delete_bettor(request):
    data = json.loads(request.body)
    acc_id = data.get('id')
    BettorAccount.objects.filter(id=acc_id).delete()
    return JsonResponse({'ok': True})


@login_required
@require_POST
def api_edit_bettor(request):
    data = json.loads(request.body)
    acc_id = data.get('id')
    try:
        acc = BettorAccount.objects.get(id=acc_id)
    except BettorAccount.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Account not found'})
    if 'phone' in data:
        acc.phone = (data['phone'] or '').strip()
    if 'balance' in data:
        acc.balance = int(data['balance'] or 0)
    if 'hot_limits' in data:
        acc.hot_limits = data['hot_limits'] or {}
    if 'multiplier' in data:
        m = int(data['multiplier'] or 10)
        acc.multiplier = m if m >= 1 else 10
    password = (data.get('password') or '').strip()
    if password:
        acc.set_password(password)
    acc.save()
    return JsonResponse({'ok': True, 'account': acc.to_dict()})


def bettor_login_page(request):
    return render(request, 'twodapp/bettor_login.html')


@login_required
def manage_bettors_page(request):
    return render(request, 'twodapp/manage_bettors.html')


# ===== Operator Panel (Owner accounts + Player accounts) =====
# Owner-account management is restricted to superusers only.

def _operator_serialize(u):
    return {
        'id': u.pk,
        'username': u.username,
        'email': u.email,
        'first_name': u.first_name,
        'last_name': u.last_name,
        'is_superuser': u.is_superuser,
        'is_staff': u.is_staff,
        'is_active': u.is_active,
        'last_login': u.last_login.strftime('%Y-%m-%d %H:%M') if u.last_login else '',
        'date_joined': u.date_joined.strftime('%Y-%m-%d') if u.date_joined else '',
    }


@user_passes_test(lambda u: u.is_authenticated and u.is_superuser)
def operator_panel_page(request):
    return render(request, 'twodapp/operator.html')


@user_passes_test(lambda u: u.is_authenticated and u.is_superuser)
@require_GET
def api_list_operators(request):
    users = [_operator_serialize(u) for u in User.objects.all().order_by('-is_superuser', '-is_staff', 'username')]
    return JsonResponse({'ok': True, 'operators': users})


@user_passes_test(lambda u: u.is_authenticated and u.is_superuser)
@require_POST
def api_create_operator(request):
    data = json.loads(request.body)
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    email = (data.get('email') or '').strip()
    first_name = (data.get('first_name') or '').strip()
    last_name = (data.get('last_name') or '').strip()
    is_staff = bool(data.get('is_staff'))
    is_superuser = bool(data.get('is_superuser'))
    if not username or not password:
        return JsonResponse({'ok': False, 'error': 'Username + password required'})
    if User.objects.filter(username__iexact=username).exists():
        return JsonResponse({'ok': False, 'error': f'"{username}" already exists'})
    if User.objects.filter(email__iexact=email).exists() and email:
        return JsonResponse({'ok': False, 'error': f'Email "{email}" already used'})
    user = User.objects.create_user(
        username=username, password=password, email=email,
        first_name=first_name, last_name=last_name,
        is_staff=is_staff, is_superuser=is_superuser, is_active=True,
    )
    return JsonResponse({'ok': True, 'operator': _operator_serialize(user)})


@user_passes_test(lambda u: u.is_authenticated and u.is_superuser)
@require_POST
def api_edit_operator(request):
    data = json.loads(request.body)
    uid = data.get('id')
    try:
        user = User.objects.get(id=uid)
    except User.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Owner account not found'})
    # Do not allow a superuser to demote/disable themselves (lockout guard).
    if user.pk == request.user.pk:
        is_superuser = user.is_superuser
        is_staff = user.is_staff
        is_active = user.is_active
    else:
        is_superuser = bool(data.get('is_superuser', user.is_superuser))
        is_staff = bool(data.get('is_staff', user.is_staff))
        is_active = bool(data.get('is_active', user.is_active))
    user.email = (data.get('email') if 'email' in data else user.email) or ''
    if 'first_name' in data:
        user.first_name = (data.get('first_name') or '').strip()
    if 'last_name' in data:
        user.last_name = (data.get('last_name') or '').strip()
    if user.pk != request.user.pk:
        user.is_superuser = is_superuser
        user.is_staff = is_staff
        user.is_active = is_active
    password = (data.get('password') or '').strip()
    if password:
        user.set_password(password)
    user.save()
    return JsonResponse({'ok': True, 'operator': _operator_serialize(user)})


@user_passes_test(lambda u: u.is_authenticated and u.is_superuser)
@require_POST
def api_reset_operator_password(request):
    data = json.loads(request.body)
    uid = data.get('id')
    password = (data.get('password') or '').strip()
    if not password:
        return JsonResponse({'ok': False, 'error': 'Password required'})
    try:
        user = User.objects.get(id=uid)
    except User.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Owner account not found'})
    user.set_password(password)
    user.save()
    return JsonResponse({'ok': True})


@user_passes_test(lambda u: u.is_authenticated and u.is_superuser)
@require_POST
def api_delete_operator(request):
    data = json.loads(request.body)
    uid = data.get('id')
    try:
        user = User.objects.get(id=uid)
    except User.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Owner account not found'})
    if user.pk == request.user.pk:
        return JsonResponse({'ok': False, 'error': 'မိမိကိုယ်တိုင်ရဲ့ အကောင့်ကို ဖျက်လို့ မရပါ'})
    user.delete()
    return JsonResponse({'ok': True})


@require_POST
def api_bettor_login(request):
    data = json.loads(request.body)
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    try:
        acc = BettorAccount.objects.get(username=username, is_active=True)
    except BettorAccount.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Account not found'})
    if not acc.check_password(password):
        return JsonResponse({'ok': False, 'error': 'Wrong password'})
    from django.utils import timezone
    acc.last_user_agent = request.META.get('HTTP_USER_AGENT', '')[:300]
    acc.last_ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))[:50]
    acc.last_seen = timezone.now()
    acc.save()
    request.session['bettor_account_id'] = acc.pk
    request.session['bettor_username'] = acc.username
    return JsonResponse({'ok': True, 'redirect': '/bet/?type=bettor'})


@login_required
@require_GET
def api_bettor_profile(request):
    acc_id = request.session.get('bettor_account_id')
    if not acc_id:
        return JsonResponse({'ok': False, 'error': 'Not logged in as bettor'})
    try:
        acc = BettorAccount.objects.get(pk=acc_id)
    except BettorAccount.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Account not found'})
    return JsonResponse({'ok': True, 'account': acc.to_dict()})


@api_login_required
def chat_page(request):
    return render(request, 'twodapp/chat.html', {'chat_role': 'owner'})


@api_login_required
def settings_page(request):
    is_owner = request.user.is_authenticated
    state = GameState.get_state()
    return render(request, 'twodapp/settings.html', {
        'is_owner': is_owner,
        'global_limit': state.global_limit or '',
        'specific_limits_json': json.dumps(dict(state.specific_limits)),
    })


@require_POST
@api_login_required
def api_change_password(request):
    data = json.loads(request.body)
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')
    if not old_password or not new_password:
        return JsonResponse({'ok': False, 'error': 'Passwords required'})
    if len(new_password) < 4:
        return JsonResponse({'ok': False, 'error': 'Password must be at least 4 characters'})
    user = request.user
    if not user.check_password(old_password):
        return JsonResponse({'ok': False, 'error': 'Wrong current password'})
    user.set_password(new_password)
    user.save()
    return JsonResponse({'ok': True})


@api_login_required
def bettor_chat_page(request):
    return render(request, 'twodapp/chat.html', {'chat_role': 'player'})


def chat_identity(request):
    if request.user.is_authenticated:
        return 'owner', request.user.username
    return 'player', request.session.get('bettor_username', 'Player')


@require_POST
@api_login_required
def api_chat_send(request):
    data = json.loads(request.body)
    message = (data.get('message') or '').strip()
    if not message:
        return JsonResponse({'ok': False, 'error': 'Empty message'})
    sender_type, sender_name = chat_identity(request)
    reply_to = None
    if data.get('reply_to'):
        try:
            reply_to = ChatMessage.objects.get(pk=int(data['reply_to']))
        except (ChatMessage.DoesNotExist, ValueError, TypeError):
            reply_to = None
    msg = ChatMessage.objects.create(
        sender_type=sender_type, sender_name=sender_name,
        message=message, reply_to=reply_to,
    )
    return JsonResponse({'ok': True, 'msg_id': msg.id})


@require_GET
@api_login_required
def api_chat_poll(request):
    after_id_str = request.GET.get('after', '0') or '0'
    try:
        after_id = int(after_id_str)
    except (ValueError, TypeError):
        after_id = 0
    last_sync = request.GET.get('sync', '')
    me_type, me_name = chat_identity(request)
    # Update my presence (last seen)
    presence, _ = ChatPresence.objects.get_or_create(user_type=me_type, user_name=me_name)
    presence.last_seen = timezone.now()

    # Mark messages from the other party as read when I poll and bump updated_at
    # so the sender's read-receipt ticks refresh.
    unread = list(ChatMessage.objects.exclude(sender_type=me_type).filter(is_read=False))
    if unread:
        ChatMessage.objects.filter(pk__in=[m.pk for m in unread]).update(
            is_read=True, updated_at=timezone.now())

    # Delta query: new messages (id > after_id) OR messages modified since last_sync.
    q_conditions = Q(id__gt=after_id)
    if last_sync:
        try:
            ts = datetime.fromisoformat(last_sync.replace('Z', '+00:00'))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            q_conditions |= Q(updated_at__gt=ts)
        except (ValueError, TypeError):
            pass
    msgs = list(ChatMessage.objects.filter(q_conditions).order_by('id')[:300])

    data = []
    by_id = {}
    for m in msgs:
        by_id[m.id] = m
    for m in msgs:
        reactions = {}
        for r in m.reactions.all():
            reactions.setdefault(r.emoji, {'count': 0, 'users': []})
            reactions[r.emoji]['count'] += 1
            reactions[r.emoji]['users'].append(f"{r.user_type}:{r.user_name}")
        reply = by_id.get(m.reply_to_id) if m.reply_to_id else None
        data.append({
            'id': m.id,
            'sender_type': m.sender_type,
            'sender_name': m.sender_name,
            'message': '' if m.is_deleted else m.message,
            'photo': (m.photo.url if m.photo else None) and (None if m.is_deleted else m.photo.url),
            'audio': m.audio.url if (m.audio and not m.is_deleted) else None,
            'is_deleted': m.is_deleted,
            'is_pinned': m.is_pinned,
            'edited': bool(m.edited_at),
            'read': m.is_read,
            'time': m.created_at.astimezone(MMT).strftime('%H:%M'),
            'date': m.created_at.astimezone(MMT).strftime('%Y-%m-%d'),
            'reply_to': {
                'id': reply.id,
                'sender_type': reply.sender_type,
                'sender_name': reply.sender_name,
                'message': reply.message if not reply.is_deleted else '',
                'is_deleted': reply.is_deleted,
                'photo': reply.photo.url if (reply.photo and not reply.is_deleted) else None,
                'audio': reply.audio.url if (reply.audio and not reply.is_deleted) else None,
            } if reply else None,
            'reactions': reactions,
        })
    presence.save(update_fields=['last_seen'])

    # Presence of the other party
    other_type = 'player' if me_type == 'owner' else 'owner'
    other_presence = ChatPresence.objects.filter(user_type=other_type).first()
    now = timezone.now()
    if other_presence:
        delta = (now - other_presence.last_seen).total_seconds()
        other_online = delta < 90
        other_typing = other_presence.is_typing and other_online
    else:
        other_presence = None
        other_online = False
        other_typing = False

    return JsonResponse({'ok': True, 'messages': data, 'server_time': now.isoformat(), 'presence': {
        'online': other_online,
        'typing': other_typing,
        'last_seen': other_presence.last_seen.astimezone(MMT).strftime('%H:%M') if other_presence else None,
    }})


@require_POST
@api_login_required
def api_chat_clear(request):
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False, 'error': 'Owner only'})
    ChatMessage.objects.all().delete()
    return JsonResponse({'ok': True})


@require_POST
@api_login_required
def api_chat_edit(request):
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False, 'error': 'Owner only'})
    data = json.loads(request.body)
    msg_id = data.get('id')
    message = (data.get('message') or '').strip()
    me_type, me_name = chat_identity(request)
    try:
        msg = ChatMessage.objects.get(pk=msg_id)
    except ChatMessage.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Not found'})
    if msg.sender_type != me_type:
        return JsonResponse({'ok': False, 'error': 'Cannot edit others'})
    if not message:
        return JsonResponse({'ok': False, 'error': 'Empty message'})
    msg.message = message
    msg.edited_at = timezone.now()
    msg.updated_at = timezone.now()
    msg.save(update_fields=['message', 'edited_at', 'updated_at'])
    return JsonResponse({'ok': True})


@require_POST
@api_login_required
def api_chat_delete(request):
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False, 'error': 'Owner only'})
    data = json.loads(request.body)
    msg_id = data.get('id')
    try:
        msg = ChatMessage.objects.get(pk=msg_id)
    except ChatMessage.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Not found'})
    msg.is_deleted = True
    msg.message = ''
    msg.updated_at = timezone.now()
    msg.save(update_fields=['is_deleted', 'message', 'updated_at'])
    return JsonResponse({'ok': True})


@require_POST
@api_login_required
def api_chat_typing(request):
    data = json.loads(request.body)
    is_typing = bool(data.get('typing'))
    me_type, me_name = chat_identity(request)
    presence, _ = ChatPresence.objects.get_or_create(user_type=me_type, user_name=me_name)
    presence.is_typing = is_typing
    presence.last_seen = timezone.now()
    presence.save(update_fields=['is_typing', 'last_seen'])
    return JsonResponse({'ok': True})


@require_POST
@api_login_required
def api_chat_pin(request):
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False, 'error': 'Owner only'})
    data = json.loads(request.body)
    msg_id = data.get('id')
    try:
        msg = ChatMessage.objects.get(pk=msg_id)
    except ChatMessage.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Not found'})
    msg.is_pinned = not msg.is_pinned
    msg.updated_at = timezone.now()
    msg.save(update_fields=['is_pinned', 'updated_at'])
    return JsonResponse({'ok': True, 'is_pinned': msg.is_pinned})


EMOJIS = ['👍', '❤️', '😂', '😮', '😢', '🔥', '💯', '🙏']


@require_POST
@api_login_required
def api_chat_react(request):
    data = json.loads(request.body)
    msg_id = data.get('id')
    emoji = data.get('emoji', '')
    if emoji not in EMOJIS:
        return JsonResponse({'ok': False, 'error': 'Invalid emoji'})
    try:
        msg = ChatMessage.objects.get(pk=msg_id)
    except ChatMessage.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Not found'})
    if request.user.is_authenticated:
        user_type, user_name = 'owner', request.user.username
    else:
        user_type = 'player'
        user_name = request.session.get('bettor_username', 'Player')
    existing = ChatReaction.objects.filter(message=msg, emoji=emoji, user_type=user_type, user_name=user_name)
    if existing.exists():
        existing.delete()
        toggled = False
    else:
        ChatReaction.objects.create(message=msg, emoji=emoji, user_type=user_type, user_name=user_name)
        toggled = True
    reactions = {}
    for r in msg.reactions.all():
        reactions.setdefault(r.emoji, {'count': 0, 'users': []})
        reactions[r.emoji]['count'] += 1
        reactions[r.emoji]['users'].append(f"{r.user_type}:{r.user_name}")
    msg.updated_at = timezone.now()
    msg.save(update_fields=['updated_at'])
    return JsonResponse({'ok': True, 'toggled': toggled, 'reactions': reactions})


@require_POST
@api_login_required
def api_chat_upload_photo(request):
    photo = request.FILES.get('photo')
    if not photo:
        return JsonResponse({'ok': False, 'error': 'No photo'})
    if photo.size > 5 * 1024 * 1024:
        return JsonResponse({'ok': False, 'error': 'Max 5MB'})
    if not photo.content_type.startswith('image/'):
        return JsonResponse({'ok': False, 'error': 'Images only'})
    caption = request.POST.get('caption', '').strip()
    if request.user.is_authenticated:
        sender_type, sender_name = 'owner', request.user.username
    else:
        sender_type = 'player'
        sender_name = request.session.get('bettor_username', 'Player')
    msg = ChatMessage.objects.create(
        sender_type=sender_type, sender_name=sender_name,
        message=caption, photo=photo
    )
    photo_url = msg.photo.url
    return JsonResponse({'ok': True, 'photo_url': photo_url, 'msg_id': msg.id})


@require_POST
@api_login_required
def api_chat_upload_audio(request):
    audio = request.FILES.get('audio')
    if not audio:
        return JsonResponse({'ok': False, 'error': 'No audio'})
    if audio.size > 10 * 1024 * 1024:
        return JsonResponse({'ok': False, 'error': 'Max 10MB'})
    if not audio.content_type.startswith('audio/'):
        return JsonResponse({'ok': False, 'error': 'Audio only'})
    sender_type, sender_name = chat_identity(request)
    msg = ChatMessage.objects.create(
        sender_type=sender_type, sender_name=sender_name,
        message='', audio=audio
    )
    return JsonResponse({'ok': True, 'audio_url': msg.audio.url, 'msg_id': msg.id})
