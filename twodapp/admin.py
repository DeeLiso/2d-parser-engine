from django.contrib import admin

from .models import GameState, OperationLog


@admin.register(GameState)
class GameStateAdmin(admin.ModelAdmin):
    list_display = ('slug', 'global_limit', 'total_amount', 'valid_lines', 'updated_at')


@admin.register(OperationLog)
class OperationLogAdmin(admin.ModelAdmin):
    list_display = ('formula', 'original', 'count', 'amount', 'is_error', 'created_at')
    list_filter = ('formula', 'is_error')
