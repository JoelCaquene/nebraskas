from django.contrib import admin, messages
from django.utils.safestring import mark_safe
from decimal import Decimal
from .models import (
    CustomUser, 
    PlatformSettings, 
    Level, 
    BankDetails, 
    Deposit, 
    Withdrawal, 
    Task, 
    Roulette, 
    RouletteSettings, 
    UserLevel, 
    PlatformBankDetails
)

@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    # 1. MODIFICADO: Mostra afiliados, investidores e tarefas de estagiários
    list_display = (
        'phone_number', 
        'available_balance', 
        'get_afiliados_count', 
        'get_investidores_count',
        'get_tarefas_estagiario',
        'is_staff', 
        'is_active', 
        'date_joined'
    )
    search_fields = ('phone_number', 'invite_code')
    list_filter = ('is_staff', 'is_active', 'level_active', 'is_intern_expired')

    def get_afiliados_count(self, obj):
        return CustomUser.objects.filter(invited_by=obj).count()
    get_afiliados_count.short_description = 'Convidados'

    def get_investidores_count(self, obj):
        # Conta quantos convidados têm um nível VIP ativo
        return CustomUser.objects.filter(invited_by=obj, userlevel__is_active=True).distinct().count()
    get_investidores_count.short_description = 'Investidores'

    def get_tarefas_estagiario(self, obj):
        # 2. MODIFICADO: Mostra progresso das tarefas (mínimo 2)
        count = Task.objects.filter(user=obj).count()
        if obj.level_active:
            return mark_safe(f'<span style="color: #28a745; font-weight: bold;">VIP ({count})</span>')
        return f"{count} / 2"
    get_tarefas_estagiario.short_description = 'Tarefas (Estag.)'

@admin.register(PlatformSettings)
class PlatformSettingsAdmin(admin.ModelAdmin):
    list_display = ('id', 'whatsapp_link', 'history_text', 'deposit_instruction', 'withdrawal_instruction')
    search_fields = ('whatsapp_link',)

@admin.register(Level)
class LevelAdmin(admin.ModelAdmin):
    list_display = ('name', 'deposit_value', 'daily_gain', 'monthly_gain', 'cycle_days')
    search_fields = ('name',)

@admin.register(BankDetails)
class BankDetailsAdmin(admin.ModelAdmin):
    list_display = ('user', 'bank_name', 'account_holder_name', 'IBAN')
    search_fields = ('user__phone_number', 'bank_name', 'account_holder_name')

@admin.register(PlatformBankDetails)
class PlatformBankDetailsAdmin(admin.ModelAdmin):
    list_display = ('get_type_icon', 'type', 'bank_name', 'account_holder_name', 'IBAN_preview')
    list_filter = ('type', 'bank_name')
    search_fields = ('bank_name', 'account_holder_name', 'IBAN')
    
    fieldsets = (
        ('Configuração de Destino', {
            'fields': ('type',),
            'description': 'Selecione se esta entrada é para pagamentos PIX ou Cripto USDT.'
        }),
        ('Dados da Conta / Carteira', {
            'fields': ('bank_name', 'account_holder_name', 'IBAN'),
        }),
    )

    def get_type_icon(self, obj):
        if obj.type == 'PIX':
            return mark_safe('<span style="color: #32BCAD; font-weight: bold;">💎 PIX</span>')
        return mark_safe('<span style="color: #F3BA2F; font-weight: bold;">🪙 USDT</span>')
    get_type_icon.short_description = 'Tipo'

    def IBAN_preview(self, obj):
        if obj.IBAN:
            return obj.IBAN[:20] + "..." if len(obj.IBAN) > 20 else obj.IBAN
        return "-"
    IBAN_preview.short_description = 'Chave / Endereço'

    class Media:
        css = {
            'all': ('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css',)
        }

@admin.register(Deposit)
class DepositAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'is_approved', 'created_at', 'proof_link') 
    search_fields = ('user__phone_number',)
    list_filter = ('is_approved',)
    readonly_fields = ('current_proof_display',)

    # 3. MODIFICADO: Soma saldo imediatamente ao marcar como aprovado
    def save_model(self, request, obj, form, change):
        if change:
            old_deposit = Deposit.objects.get(pk=obj.pk)
            if not old_deposit.is_approved and obj.is_approved:
                user = obj.user
                user.available_balance += obj.amount
                user.save()
                messages.success(request, f"Saldo de {obj.amount} creditado para {user.phone_number}")
        super().save_model(request, obj, form, change)

    def proof_link(self, obj):
        if obj.proof_of_payment:
            return mark_safe(f'<a href="{obj.proof_of_payment.url}" target="_blank">Ver Comprovativo</a>')
        return "Nenhum"
    proof_link.short_description = 'Comprovativo'

    def current_proof_display(self, obj):
        if obj.proof_of_payment:
            return mark_safe(f'''
                <a href="{obj.proof_of_payment.url}" target="_blank">Ver Imagem em Tamanho Real</a><br/>
                <img src="{obj.proof_of_payment.url}" style="max-width:300px; height:auto; margin-top: 10px;" />
            ''')
        return "Nenhum Comprovativo Carregado"
    current_proof_display.short_description = 'Comprovativo Atual'

@admin.register(Withdrawal)
class WithdrawalAdmin(admin.ModelAdmin):
    # 4. MODIFICADO: IBAN aparece na lista e botão de aprovação rápida
    list_display = (
        'user', 
        'get_valor_bruto_kz', 
        'get_valor_liquido_kz',
        'get_pagamento_real_brl', 
        'get_iban_direto', # Solicitação: IBAN aparece imediatamente
        'status', 
        'botao_aprovar_rapido' # Solicitação: Apenas clique para aprovar
    )
    
    list_filter = ('status', 'created_at')
    search_fields = ('user__phone_number', 'user__full_name')

    readonly_fields = (
        'get_valor_bruto_kz', 
        'get_taxa_descontada_kz', 
        'get_valor_liquido_kz', 
        'get_pagamento_real_brl',
        'get_dados_bancarios',
        'created_at'
    )

    fieldsets = (
        ('Informações do Cliente', {
            'fields': ('user', 'status', 'created_at')
        }),
        ('Cálculos Financeiros (Câmbio Wise)', {
            'fields': (
                'get_valor_bruto_kz', 
                'get_taxa_descontada_kz', 
                'get_valor_liquido_kz', 
                'get_pagamento_real_brl'
            )
        }),
        ('Logística de Pagamento', {
            'fields': ('get_dados_bancarios',)
        }),
        ('Dados Técnicos', {
            'fields': ('amount',),
            'classes': ('collapse',),
        }),
    )
    
    CAMBIO_WISE = Decimal('0.0065')
    TAXA_PERCENTUAL = Decimal('0.10')

    def get_valor_bruto_kz(self, obj):
        return f"{obj.amount:,.2f} Kz".replace(",", "X").replace(".", ",").replace("X", ".")
    get_valor_bruto_kz.short_description = 'Bruto'

    def get_taxa_descontada_kz(self, obj):
        taxa = obj.amount * self.TAXA_PERCENTUAL
        return mark_safe(f'<span style="color: #d9534f;">- {taxa:,.2f} Kz</span>')
    get_taxa_descontada_kz.short_description = 'Taxa (10%)'

    def get_valor_liquido_kz(self, obj):
        liquido = obj.amount * (Decimal('1') - self.TAXA_PERCENTUAL)
        return mark_safe(f'<b>{liquido:,.2f} Kz</b>')
    get_valor_liquido_kz.short_description = 'Líquido'

    def get_pagamento_real_brl(self, obj):
        liquido_kz = obj.amount * (Decimal('1') - self.TAXA_PERCENTUAL)
        valor_brl = liquido_kz * self.CAMBIO_WISE
        return mark_safe(
            f'<div style="background: #e6fffa; padding: 5px 10px; border-radius: 4px; border: 1px solid #38b2ac; display: inline-block;">'
            f'<b style="color: #2c7a7b;">R$ {valor_brl:,.2f}</b>'
            f'</div>'
        )
    get_pagamento_real_brl.short_description = 'PAGAR (BRL)'

    def get_iban_direto(self, obj):
        try:
            dados = BankDetails.objects.get(user=obj.user)
            return mark_safe(f'<code style="color:#e83e8c; font-weight:bold;">{dados.IBAN}</code>')
        except BankDetails.DoesNotExist:
            return mark_safe("<span style='color:red;'>Sem Dados</span>")
    get_iban_direto.short_description = 'IBAN/PIX'

    def get_dados_bancarios(self, obj):
        try:
            dados = BankDetails.objects.get(user=obj.user)
            return mark_safe(
                f"<div style='background:#f9f9f9; padding:10px; border-radius:8px; border:1px solid #ddd;'>"
                f"<b>Titular:</b> {dados.account_holder_name}<br>"
                f"<b>Banco:</b> {dados.bank_name}<br>"
                f"<b>IBAN:</b> {dados.IBAN}"
                f"</div>"
            )
        except BankDetails.DoesNotExist:
            return "Sem dados cadastrados."
    get_dados_bancarios.short_description = 'Dados para Depósito'

    def botao_aprovar_rapido(self, obj):
        if obj.status == 'Pendente' or obj.status == 'Pending':
            return mark_safe(
                f'<a class="button" href="?set_status=Aprovado&idx={obj.id}" '
                f'style="background-color: #28a745; color: white; padding: 5px 10px; border-radius: 4px; text-decoration: none;">'
                f'Aprovar Agora</a>'
            )
        elif obj.status == 'Aprovado':
            return mark_safe("<span style='color:#28a745; font-weight:bold;'>✓ Pago</span>")
        return obj.status
    botao_aprovar_rapido.short_description = 'Aprovação'

    def changelist_view(self, request, extra_context=None):
        if 'set_status' in request.GET and 'idx' in request.GET:
            status_novo = request.GET.get('set_status')
            idx = request.GET.get('idx')
            Withdrawal.objects.filter(id=idx).update(status=status_novo)
            self.message_user(request, f"Saque #{idx} aprovado!")
        return super().changelist_view(request, extra_context)

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('user', 'earnings', 'completed_at')
    search_fields = ('user__phone_number',)

@admin.register(Roulette)
class RouletteAdmin(admin.ModelAdmin):
    list_display = ('user', 'prize', 'is_approved', 'spin_date')
    search_fields = ('user__phone_number',)
    list_filter = ('is_approved',)

@admin.register(RouletteSettings)
class RouletteSettingsAdmin(admin.ModelAdmin):
    list_display = ('id', 'prizes')

@admin.register(UserLevel)
class UserLevelAdmin(admin.ModelAdmin):
    list_display = ('user', 'level', 'purchase_date', 'is_active')
    search_fields = ('user__phone_number', 'level__name')
    list_filter = ('is_active',)
    