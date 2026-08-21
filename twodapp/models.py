from django.db import models
from django.contrib.auth.hashers import make_password, check_password


class GameState(models.Model):
    """Single-row table holding the global ledger state."""
    slug = models.SlugField(unique=True, default='main')
    ledger = models.JSONField(default=list)  # list of 100 integers
    specific_limits = models.JSONField(default=dict)  # e.g. {'05': 30000}
    global_limit = models.IntegerField(default=50000)
    total_amount = models.BigIntegerField(default=0)
    valid_lines = models.IntegerField(default=0)
    bettor_name = models.CharField(max_length=100, blank=True, default='')
    bettor_date = models.CharField(max_length=10, blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Game State'

    def save(self, *args, **kwargs):
        if not isinstance(self.ledger, list) or len(self.ledger) != 100:
            self.ledger = [0] * 100
        if not isinstance(self.specific_limits, dict):
            self.specific_limits = {}
        super().save(*args, **kwargs)

    @classmethod
    def get_state(cls):
        obj, _ = cls.objects.get_or_create(slug='main', defaults={'ledger': [0] * 100})
        if len(obj.ledger) != 100:
            obj.ledger = [0] * 100
            obj.save()
        return obj


class BettorAccount(models.Model):
    username = models.CharField(max_length=50, unique=True)
    password_hash = models.CharField(max_length=128)
    phone = models.CharField(max_length=20, blank=True, default='')
    balance = models.IntegerField(default=0)
    hot_limits = models.JSONField(default=dict)  # e.g. {'23': 5000, '44': 3000}
    is_active = models.BooleanField(default=True)
    last_user_agent = models.CharField(max_length=300, blank=True, default='')
    last_ip = models.CharField(max_length=50, blank=True, default='')
    last_seen = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def set_password(self, raw):
        self.password_hash = make_password(raw)

    def check_password(self, raw):
        return check_password(raw, self.password_hash)

    def to_dict(self):
        from django.utils import timezone as tz
        return {
            'id': self.pk,
            'username': self.username,
            'phone': self.phone,
            'balance': self.balance,
            'hot_limits': self.hot_limits,
            'is_active': self.is_active,
            'last_user_agent': self.last_user_agent,
            'last_ip': self.last_ip,
            'last_seen': self.last_seen.astimezone(tz.utc).strftime('%Y-%m-%d %H:%M') if self.last_seen else '',
        }


class OperationLog(models.Model):
    formula = models.CharField(max_length=50, blank=True, default='')
    original = models.TextField(default='')
    numbers = models.JSONField(default=list, blank=True)  # generated numbers list
    count = models.IntegerField(default=0)
    amount = models.IntegerField(default=0)
    is_error = models.BooleanField(default=False)
    is_canceled = models.BooleanField(default=False)
    bettor_name = models.CharField(max_length=100, blank=True, default='')
    bettor_date = models.CharField(max_length=10, blank=True, default='')
    bettor_username = models.CharField(max_length=50, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']
